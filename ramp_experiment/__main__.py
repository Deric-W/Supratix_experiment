#!/usr/bin/python3

# run server (dont forget to set the pins 3 and 2 to GPIO mode and enable PWM)
import time
import logging
from argparse import ArgumentParser
from configparser import ConfigParser, NoOptionError
from collections import namedtuple
from contextlib import ExitStack
from threading import Event
from queue import SimpleQueue, Empty
from struct import Struct
from enum import Enum
import paho.mqtt.client as mqtt
from onionGpio import OnionGpio, Value, Direction, Edge
from onionPwm import OnionPwm
from . import __version__
from .A4988 import A4988
from .motor import WormMotor
from .ramp import Ramp


angle_struct = Struct("!d")    # angle in radians as 64 bit float

timestamp_struct = angle_struct     # unix timestamp as 64 bit float

status_struct = Struct("!B")    # status as uint8


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


class Status(Enum):
    """the status of the experiment"""
    READY = 0
    BUSY = 1
    ERROR = 2
    OFFLINE = 3

    @classmethod
    def from_bytes(cls, data: bytes):
        """convert bytes to variant"""
        return cls(status_struct.unpack(data)[0])

    def to_bytes(self) -> bytes:
        """convert variant to bytes"""
        return status_struct.pack(self.value)


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
        self.logger = logger
        self.topics = topics
        self.qos = qos
        self.target_queue = SimpleQueue()
        self.shutdown_sheduled = False
        self.is_shutdown = Event()

        self.mqtt_client.will_set(topics.status, Status.OFFLINE.to_bytes(), qos, retain=True)
        self.mqtt_client.message_callback_add(topics.target_angle, self.submit_target)
        self.mqtt_client.connect(host, port)
        if self.mqtt_client.subscribe(topics.target_angle, qos)[0] != mqtt.MQTT_ERR_SUCCESS:
            self.logger.fatal(f"failed to subscribe to {topics.target_angle}")
            raise ValueError(f"failed to subscribe to '{topics.target_angle}'")
        self.logger.info(f"connecting to {host} on port {port}")

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.shutdown()
        return False

    def submit_target(self, client: mqtt.Client, userdata, message: mqtt.MQTTMessage) -> None:
        angle = angle_struct.unpack(message.payload)[0]
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
        self.logger.debug("enable elevator")
        self.elevator.enable()
        try:
            self.logger.debug("waiting for edge")
            self.landing_zone.waitForEdge(self.landing_zone_timeout)
        except TimeoutError:
            self.logger.error("landing zone timeout expired")
            self.update_status(Status.ERROR)
        else:
            self.update_timestamp(time.time())
            self.update_status(Status.READY)
        finally:
            self.elevator.disable()
            self.logger.debug("disabled elevator")

    def update_timestamp(self, timestamp: float) -> mqtt.MQTTMessageInfo:
        """update last timestamp"""
        self.logger.info(f"updating timestamp to {timestamp}")
        return self.mqtt_client.publish(
            self.topics.last_timestamp,
            timestamp_struct.pack(timestamp),
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
            angle_struct.pack(angle),
            self.qos
        )

    def loop_forever(self) -> None:
        """process targets until stop() is called"""
        self.is_shutdown.clear()    # make stop() block
        try:
            self.update_status(Status.READY)
            self.mqtt_client.loop_start()
            while not self.shutdown_sheduled:
                try:
                    target = self.target_queue.get(timeout=1)
                    self.handle_target(target)
                except Empty:
                    pass
                except Exception as e:
                    self.logger.fatal("Exception occured while handling target", exc_info=e)
                    raise
        finally:    # prevent stop() from hanging if an exception occures
            self.is_shutdown.set()

    def stop(self) -> None:
        """stop processing targets"""
        self.logger.info("stopping loop")
        self.shutdown_sheduled = True   # tell loop_forever() to stop
        self.is_shutdown.wait()     # wait for it to stop
        self.update_status(Status.OFFLINE).wait_for_publish()   # update status and wait for messages to be send
        self.mqtt_client.loop_stop()
        self.shutdown_sheduled = False      # reset to allow calling loop_forever() again
        self.logger.info("stopped server")

    def shutdown(self) -> None:
        """shutdown server and devices"""
        self.logger.info("shutting down server and devices")
        try:
            self.stop()
            self.mqtt_client.disconnect()
        except Exception as e:
            self.logger.fatal(f"server shutdown failed with {e}")
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
        logger=server_logger,
        topics=Topics(
            config.get("topics", "status"),
            config.get("topics", "timestamp"),
            config.get("topics", "current"),
            config.get("topics", "target")
        ),
        qos=config.getint("mqtt", "qos")
    )

    stack.pop_all()     # setup successfull, shutdown is handled by server

with server:
    server.loop_forever()
