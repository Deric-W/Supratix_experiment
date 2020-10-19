#!/usr/bin/python3

# run server (dont forget to set the pins 3 and 2 to GPIO mode and enable PWM)
import logging
import signal
import time
from argparse import ArgumentParser
from collections import namedtuple
from configparser import ConfigParser, NoOptionError
from contextlib import ExitStack
from enum import Enum
from queue import Empty, SimpleQueue
from threading import Event
import paho.mqtt.client as mqtt
from onionGpio import Direction, Edge, OnionGpio, Value
from onionPwm import OnionPwm
from . import __version__
from .A4988 import A4988
from .motor import WormMotor
from .mqtt import ANGLE_STRUCT, TIMESTAMP_STRUCT, Status
from .ramp import Ramp

Topics = namedtuple(
    "Topics",
    ("status", "last_timestamp", "current_angle", "target_angle")
)


class LogLevel(Enum):
    """logelevels as strings"""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    FATAL = "fatal"

    def to_level(self) -> int:
        """convert variant to log level"""
        return getattr(logging, self.name)


class Waiter:
    """class enforcing a certain time period between actions"""
    def __init__(self, period: float) -> None:
        self.period = period
        self.timestamp = 0.0

    def reset(self) -> None:
        """reset waiter to waiting state"""
        self.timestamp = time.time()

    def wait(self) -> float:
        """wait until waiter finishes waiting, return time spend sleeping"""
        to_wait = self.period + self.timestamp - time.time()
        if to_wait > 0:
            time.sleep(to_wait)
            return to_wait
        return 0

    def is_waiting(self) -> bool:
        """return if wait() would sleep"""
        return self.period + self.timestamp > time.time()


class RampServer:
    def __init__(self,
                 host: str,
                 port: int,
                 mqtt_client: mqtt.Client,
                 ramp: Ramp,
                 step_size: float,
                 elevator: OnionPwm,
                 landing_zone: OnionGpio,
                 landing_zone_timeout: float,
                 swing_time: float,
                 logger: logging.Logger,
                 topics: Topics,
                 qos: int = 0
    ):
        self.mqtt_client = mqtt_client
        self.ramp = ramp
        self.step_size = step_size
        self.elevator = elevator
        self.landing_zone = landing_zone
        self.landing_zone_timeout = landing_zone_timeout
        self.landing_zone_waiter = Waiter(swing_time)   # use waiter to prevent pointless sleeping
        self.logger = logger
        self.topics = topics
        self.qos = qos
        self.target_queue = SimpleQueue()  # type: SimpleQueue[float]
        self.stop_scheduled = False
        self.is_stopped = Event()

        self.mqtt_client.will_set(topics.status, Status.OFFLINE.to_bytes(), qos, retain=True)   # if the onion crashes, set status to offline
        self.mqtt_client.message_callback_add(topics.target_angle, self.submit_target)
        self.mqtt_client.connect(host, port)
        if self.mqtt_client.subscribe(topics.target_angle, qos)[0] != mqtt.MQTT_ERR_SUCCESS:
            self.logger.critical(f"failed to subscribe to {topics.target_angle}")
            raise ValueError(f"failed to subscribe to '{topics.target_angle}'")
        self.logger.info(f"connecting to {host} on port {port}")

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.shutdown()
        return False

    def submit_target(self, client: mqtt.Client, userdata, message: mqtt.MQTTMessage) -> None:
        """submit target to be processed"""
        angle = ANGLE_STRUCT.unpack(message.payload)[0]
        self.logger.info(f"received angle {angle}")
        self.target_queue.put(angle)

    def handle_target(self, angle: float) -> None:
        """process a single target angle"""
        self.logger.info(f"handling angle {angle}")
        self.logger.debug(f"moving to angle {angle}")
        self.update_status(Status.BUSY)
        for _ in self.ramp.iter_angle(angle, self.step_size):
            self.update_current(self.ramp.get_angle())  # update for each step
        current_angle = self.ramp.get_angle()
        self.update_current(current_angle)  # update final angle
        self.logger.debug(f"reached angle {current_angle}")
        self.logger.debug(f"waited {self.landing_zone_waiter.wait()} seconds for landing zone to stop swinging")     # wait for oscillations to stop
        self.logger.debug("enable elevator")
        self.elevator.enable()
        try:
            self.logger.debug("waiting for edge")
            self.landing_zone.waitForEdge(self.landing_zone_timeout)
        except TimeoutError:    # marble left the experiment
            self.logger.error("landing zone timeout expired")
            self.update_status(Status.ERROR)
        else:                   # marble landed
            self.update_timestamp(time.time())
            self.update_status(Status.READY)
        finally:                # make sure to disable the elevator no matter what happens
            self.elevator.disable()
            self.logger.debug("disabled elevator")
            self.landing_zone_waiter.reset()    # make next experiment wait for oscillations of the landing zone to stop

    def update_timestamp(self, timestamp: float) -> mqtt.MQTTMessageInfo:
        """update last timestamp"""
        self.logger.info(f"updating timestamp to {timestamp}")
        return self.mqtt_client.publish(
            self.topics.last_timestamp,
            TIMESTAMP_STRUCT.pack(timestamp),
            self.qos
        )

    def update_status(self, status: Status) -> mqtt.MQTTMessageInfo:
        """update status"""
        self.logger.info(f"updating status to {status.name}")
        return self.mqtt_client.publish(
            self.topics.status,
            status.to_bytes(),
            self.qos,
            retain=True
        )

    def update_current(self, angle: float) -> mqtt.MQTTMessage:
        """update current angle"""
        self.logger.info(f"updating current angle to {angle}")
        return self.mqtt_client.publish(
            self.topics.current_angle,
            ANGLE_STRUCT.pack(angle),
            self.qos
        )

    def loop_forever(self) -> None:
        """process targets until stop() is called"""
        self.is_stopped.clear()    # make stop() block
        try:
            self.update_status(Status.READY)
            self.mqtt_client.loop_start()
            while not self.stop_scheduled:
                try:
                    target = self.target_queue.get(timeout=1)
                    self.handle_target(target)
                except Empty:   # no targets to process, check for shutdown
                    pass
                except Exception as e:  # something else happend, log exception and crash
                    self.logger.critical("Exception occured while handling target", exc_info=e)
                    raise
        finally:    # prevent stop() from hanging if an exception occures
            self.is_stopped.set()
            self.stop_scheduled = False     # reset to allow calling loop_forever() again

    def schedule_stop(self) -> None:
        """tell loop_forever() to stop processing targets"""
        self.stop_scheduled = True

    def stop(self) -> None:
        """wait for loop_forever() to stop processing targets"""
        self.logger.info("stopping loop")
        self.schedule_stop()
        self.is_stopped.wait()     # wait for it to stop
        self.update_status(Status.OFFLINE).wait_for_publish()   # update status and wait for messages to be send
        self.mqtt_client.loop_stop()
        self.stop_scheduled = False     # reset to allow calling loop_forever() again in case it was not running
        self.logger.info("stopped server")

    def shutdown(self) -> None:
        """shutdown server and devices"""
        self.logger.info("shutting down server and devices")
        try:
            self.stop()
            self.mqtt_client.disconnect()   # disconnect after .stop() to allow queued messages to be send
        except Exception as e:
            self.logger.critical("server shutdown failed", exc_info=e)
            raise   # dont hide exception
        finally:    # dont abort on error
            self.ramp.shutdown()    # shutdown devices after server to make sure they are not in use
            self.elevator.release()
            self.landing_zone.release()
        self.logger.info("shutdown server")


# parse args
parser = ArgumentParser(description="Server awaiting experiment requests for a marble ramp")
parser.add_argument(
    "-v",
    "--version",
    help="display version number",
    action="version",
    version="%(prog)s {version}".format(version=__version__)
)
parser.add_argument(
    "-c",
    "--config",
    type=str,
    help="path to custom config file",
    default="/etc/rampserver.conf"
)
args = parser.parse_args()

# parse config file
config = ConfigParser(inline_comment_prefixes=("#",))
with open(args.config, "r") as fd:
    config.read_file(fd)

# setup logging
logging.basicConfig(
    format="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    filename=config.get("logging", "file", fallback=None)   # fallback is stdout
)
server_logger = logging.getLogger("ramp_server")
mqtt_logger = logging.getLogger("paho-mqtt")
server_logger.setLevel(
    LogLevel(config.get("logging", "server_level", fallback="info")).to_level()
)
mqtt_logger.setLevel(
    LogLevel(config.get("logging", "mqtt_level", fallback="info")).to_level()
)

# setup mqtt
mqtt_client = mqtt.Client(
    config.get("mqtt", "id"),
    clean_session=config.getboolean("mqtt", "clean_session")
)
mqtt_client.enable_logger(mqtt_logger)
if config.getboolean("mqtt", "tls"):
    mqtt_client.tls_set()
try:
    username = config.get("mqtt", "username")
except NoOptionError:
    pass
else:
    mqtt_client.username_pw_set(username, config.get("mqtt", "password"))

with ExitStack() as stack:
    # setup elevator
    elevator = stack.enter_context(OnionPwm(
        config.getint("elevator", "channel"),
        config.getint("elevator", "chip"),
    ))
    elevator.set_frequency(config.getint("elevator", "frequency"))
    elevator.set_duty_cycle(config.getfloat("elevator", "duty_cycle"))

    # setup landing_zone
    landing_zone = stack.enter_context(OnionGpio(config.getint("landing_zone", "gpio")))
    landing_zone.setDirection(Direction.INPUT)
    landing_zone.setEdge(Edge.FALLING)  # prepare for edge

    # setup driver
    driver = stack.enter_context(A4988(
        config.getint("driver", "enable"),
        config.getint("driver", "sleep"),
        config.getint("driver", "step"),
        config.getint("driver", "dir")
    ))

    # setup ramp
    ramp = Ramp(
        WormMotor(
            driver,
            Value(config.get("motor", "direction")),
            config.getfloat("motor", "step_width"),
            config.getfloat("motor", "pps"),
            config.getfloat("motor", "limit_lower"),
            config.getfloat("motor", "limit_upper")
        ),
        config.getfloat("ramp", "base_length"),
        config.getfloat("ramp", "offset")
    )

    # setup server
    server = RampServer(
        host=config.get("mqtt", "host"),
        port=config.getint("mqtt", "port"),
        mqtt_client=mqtt_client,
        ramp=ramp,
        step_size=config.getfloat("ramp", "step_size"),
        elevator=elevator,
        landing_zone=landing_zone,
        landing_zone_timeout=config.getfloat("landing_zone", "timeout"),
        swing_time=config.getfloat("landing_zone", "swing_time"),
        logger=server_logger,
        topics=Topics(
            config.get("topics", "status"),
            config.get("topics", "timestamp"),
            config.get("topics", "current"),
            config.get("topics", "target")
        ),
        qos=config.getint("mqtt", "qos")
    )

    signal.signal(signal.SIGTERM, lambda signum, frame: server.schedule_stop())    # schedule shutdown of server loop, cleanup is handled by with statement

    stack.pop_all()     # setup successfull, shutdown is handled by server

with server:
    server.loop_forever()
