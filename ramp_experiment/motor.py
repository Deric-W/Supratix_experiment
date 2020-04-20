#!/usr/bin/python3

"""Module for controlling the stepper motor"""

import time
from .A4988 import STEP_SLEEP

class OutOfRangeError(Exception):
    """Exception raised if the desired position is out of the range of the motor"""
    pass


class WormMotor:
    """class for using motors with a worm gear"""
    def __init__(self, driver, direction, step_width, pps, limit_lower, limit_upper, position=0, reset_on_shutdown=True):
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
        self.steps = int(limit_lower / step_width)
        self.starting_steps = int(limit_lower / step_width)
        self.reset_on_shutdown = reset_on_shutdown

    def __enter__(self):
        return self
    
    def __exit__(self, type, value, traceback):
        self.shutdown()
        return False    # we dont handle exceptions

    def shutdown(self):
        """shutdown motor and driver"""
        if self.reset_on_shutdown:
            self.set_steps(self.starting_steps)
        self.driver.shutdown()
    
    def _move_steps(self, amount, direction):
        """move amount steps in direction"""
        self.driver.set_direction(direction)
        self.driver.wake()
        try:
            for _ in range(amount):
                self.driver.step()
                time.sleep(self.tps - STEP_SLEEP * 2)
        finally:
            self.driver.sleep() # prevent overheating if exception
    
    def set_steps(self, steps):
        """set absolute step count"""
        if self.limit_upper >= steps >= self.limit_lower:
            diff = steps - self.steps
            if diff > 0:  # step count has to be increased
                self._move_steps(diff, self.direction)
            elif diff < 0:  # step count has to be decreased
                self._move_steps(-diff, 1 if self.direction == 0 else 0)
            else:   # step already reached
                pass
            self.steps = steps
        else:
            raise OutOfRangeError("step count {0} exceeds limits of {1} (lower) and {2} (upper)".format(steps, self.limit_lower, self.limit_upper))

    def get_steps(self):
        """get absolute step count"""
        return self.steps

    def set_position(self, position):
        """set new position"""
        self.set_steps(int(position / self.step_width))

    def get_position(self):
        """get current position"""
        return self.steps * self.step_width
