#!/usr/bin/python3

"""Module for using the A4988 driver with the onion omega"""
# datasheet: https://www.pololu.com/file/0J450/a4988_DMOS_microstepping_driver_with_translator.pdf

import time
from onionGpio import OnionGpio, Value, Direction

WAKE_SLEEP = 0.001  # one ms
STEP_SLEEP = 0.000001   # one µs

class A4988:
    """Class implementing the A4988 support"""
    def __init__(self, enable: int, sleep: int, step: int, dir: int, ignore_busy: bool=False) -> None:
        """init with gpio pins for the enable, sleep, step and direction pin and if they should be used even if they are exported by another program"""
        self.gpio_enable = OnionGpio(enable, ignore_busy=ignore_busy)
        self.gpio_enable.setDirection(Direction.OUTPUT_HIGH)  # disable driver
        self.gpio_sleep = OnionGpio(sleep, ignore_busy=ignore_busy)
        self.gpio_sleep.setDirection(Direction.OUTPUT_HIGH)   # do not sleep
        self.gpio_step = OnionGpio(step, ignore_busy=ignore_busy)
        self.gpio_step.setDirection(Direction.OUTPUT_LOW) 
        self.gpio_dir = OnionGpio(dir, ignore_busy=ignore_busy)
        self.gpio_dir.setDirection(Direction.OUTPUT_LOW)

    def __enter__(self):
        return self
    
    def __exit__(self, type, value, traceback):
        self.shutdown()
        return False    # we dont handle exceptions

    def shutdown(self) -> None:
        """shutdown driver and gpio"""
        self.sleep()    # save energy
        self.disable()  # prevent motor from overheating
        self.gpio_enable.release()
        self.gpio_sleep.release()
        self.gpio_step.release()
        self.gpio_dir.release()
    
    def enable(self) -> None:
        """enable driver"""
        self.gpio_enable.setValue(Value.LOW)
    
    def disable(self) -> None:
        """disable driver"""
        self.gpio_enable.setValue(Value.HIGH)
    
    def is_enabled(self) -> bool:
        """return if the driver is enabled"""
        return self.gpio_enable.getValue() == Value.LOW

    def sleep(self) -> None:
        """set the driver to sleep mode"""
        self.gpio_sleep.setValue(Value.LOW)
    
    def wake(self) -> None:
        """wake driver from sleep mode"""
        self.gpio_sleep.setValue(Value.HIGH)
        time.sleep(WAKE_SLEEP)   # allow driver to wake up

    def is_sleeping(self) -> bool:
        """return if the driver is in sleep mode"""
        return self.gpio_sleep.getValue() == Value.LOW

    def set_direction(self, direction: Value) -> None:
        """set direction of the driver"""
        self.gpio_dir.setValue(direction)
    
    def get_direction(self) -> Value:
        """get direction of the driver"""
        return self.gpio_dir.getValue()
    
    def step(self) -> None:
        """make the motor do a step"""
        self.gpio_step.setValue(Value.HIGH)
        time.sleep(STEP_SLEEP)
        self.gpio_step.setValue(Value.LOW)
        time.sleep(STEP_SLEEP)
