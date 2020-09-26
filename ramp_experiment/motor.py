#!/usr/bin/python3

"""Module for controlling the stepper motor"""

import time
import math
from .A4988 import STEP_SLEEP
from onionGpio import Value


class OutOfRangeError(Exception):
    """Exception raised if the desired position is out of the range of the motor"""
    pass


class WormMotor:
    """class for using motors with a worm gear"""
    def __init__(
            self,
            driver,
            direction: Value,
            step_width: float,
            pps: float,
            limit_lower: float = -math.inf,
            limit_upper: float = math.inf,
            position: int = 0,
            reset_on_shutdown: bool = True
    ) -> None:
        """init with motor driver, driver direction to increase position, step width, pulses per second,
        motor movement range, lower and upper limit, current position and if the position should be reset on shutdown"""
        driver.sleep()  # save energy
        driver.enable()  # be operational after wake
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
        finally:    # shutdown driver even if an error occurs while reaching the position
            self.driver.shutdown()

    def _move_steps(self, amount: int, direction: Value) -> None:
        """move amount steps in direction"""
        self.driver.set_direction(direction)
        self.driver.wake()
        try:
            for _ in range(amount):
                self.driver.step()
                if direction == self.direction:  # set steps immediately to prevent step loss if a exception occures
                    self.steps += 1
                else:
                    self.steps -= 1
                time.sleep(self.tps - STEP_SLEEP * 2)
        finally:    # sleep even if an error occurs
            self.driver.sleep()  # prevent overheating and save energy

    def set_steps(self, steps: int) -> None:
        """set absolute step count"""
        if self.limit_upper >= steps >= self.limit_lower:
            difference = steps - self.steps
            if difference > 0:    # step count has to be increased
                self._move_steps(difference, self.direction)
            elif difference < 0:  # step count has to be decreased
                self._move_steps(-difference, Value.HIGH if self.direction is Value.LOW else Value.LOW)   # change diff to positive number and toggle direction
            else:           # step already reached
                pass
        else:
            raise OutOfRangeError("step count {0} exceeds limits of {1} (lower) and {2} (upper)".format(steps, self.limit_lower, self.limit_upper))

    def iter_steps(self, steps: int, step_size: int):
        """set steps and yield control after doing 'step_size' steps"""
        if step_size <= 0:
            raise ValueError("step_size is not a positive number")
        elif self.limit_upper >= steps >= self.limit_lower:
            difference = steps - self.steps
            if difference < 0:    # step count has to be decreased
                difference = -difference
                direction = Value.HIGH if self.direction is Value.LOW else Value.LOW    # toggle direction
            else:
                direction = self.direction
            while difference > step_size:               # while we can do at least one more step without reaching 'steps'
                yield self._move_steps(step_size, direction)  # move step_size steps and yield control
                difference -= step_size                 # update difference
            self._move_steps(difference, direction)     # move remaining steps
        else:
            raise OutOfRangeError("step count {0} exceeds limits of {1} (lower) and {2} (upper)".format(steps, self.limit_lower, self.limit_upper))

    def get_steps(self) -> int:
        """get absolute step count"""
        return self.steps

    def set_position(self, position: float) -> None:
        """set new position"""
        self.set_steps(int(position / self.step_width))     # convert from position to full steps

    def iter_position(self, position: float, step_size: float):
        """set position and yield control after moving a 'step_size' distance"""
        yield from self.iter_steps(int(position / self.step_width), int(step_size / self.step_width))   # convert from position and distance to full steps

    def get_position(self) -> float:
        """get current position"""
        return self.steps * self.step_width     # convert from steps to position
