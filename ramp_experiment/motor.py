#!/usr/bin/python3

"""Module for controlling the stepper motor"""

import time
from .A4988 import STEP_SLEEP
from onionGpio import Value

class OutOfRangeError(Exception):
    """Exception raised if the desired position is out of the range of the motor"""
    pass


class WormMotor:
    """class for using motors with a worm gear"""
    def __init__(self, driver, direction: Value, step_width: float, pps: float, limit_lower: float, limit_upper: float, position: int=0, reset_on_shutdown: bool=True) -> None:
        """init with motor driver, driver direction to increase position, step width, pulses per second,
        motor movement range, lower and upper limit, current position and if the position should be reset on shutdown"""
        driver.sleep()  # save energy
        driver.enable() # to be operational after wake
        self.driver = driver
        self.direction = direction
        self.step_width = step_width
        self.tps = 1 / pps  # time per pulse
        self.limit_lower = int(limit_lower / step_width)  # covert all positions from width to steps
        self.limit_upper = int(limit_upper / step_width)
        self.steps = int(position / step_width)
        self.reset_on_shutdown = reset_on_shutdown

    def __enter__(self):
        return self
    
    def __exit__(self, type, value, traceback):
        self.shutdown()
        return False    # we dont handle exceptions

    def shutdown(self) -> None:
        """shutdown motor and driver"""
        try:
            if self.reset_on_shutdown:
                self.set_steps(self.limit_lower)
        finally:
            self.driver.shutdown()
    
    def _move_steps(self, amount: int, direction: Value) -> None:
        """move amount steps in direction"""
        self.driver.set_direction(direction)
        self.driver.wake()
        try:
            for _ in range(amount):
                self.driver.step()
                if direction == self.direction: # set steps immediately to prevent step loss if a exception occures
                    self.steps += 1
                else:
                    self.steps -= 1
                time.sleep(self.tps - STEP_SLEEP * 2)
        finally:
            self.driver.sleep() # prevent overheating if exception
    
    def set_steps(self, steps: int) -> None:
        """set absolute step count"""
        if self.limit_upper >= steps >= self.limit_lower:
            diff = steps - self.steps
            if diff > 0:  # step count has to be increased
                self._move_steps(diff, self.direction)
            elif diff < 0:  # step count has to be decreased
                self._move_steps(-diff, Value.HIGH if self.direction == Value.LOW else Value.LOW)
            else:   # step already reached
                pass
        else:
            raise OutOfRangeError("step count {0} exceeds limits of {1} (lower) and {2} (upper)".format(steps, self.limit_lower, self.limit_upper))

    def get_steps(self) -> int:
        """get absolute step count"""
        return self.steps

    def set_position(self, position: float) -> None:
        """set new position"""
        self.set_steps(int(position / self.step_width))

    def get_position(self) -> float:
        """get current position"""
        return self.steps * self.step_width
