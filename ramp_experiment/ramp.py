#!/usr/bin/python3

"""Module for controlling the ramp"""

import math


class Ramp:
    def __init__(self, motor, adjacent: float, offset: float = 0) -> None:
        """init with motor object, the length of the side of the ramp adjacent to the angle and a angle offset in radians"""
        self.motor = motor
        self.adjacent = adjacent
        self.offset = math.tan(offset) * adjacent   # store as position offset because tan(x+y) != tan(x) + tan(y)

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.shutdown()
        return False    # we dont handle exceptions

    def shutdown(self) -> None:
        """shutdown ramp motor"""
        self.motor.shutdown()

    def set_angle(self, radians: float) -> None:
        """set ramp angle in radians"""
        self.motor.set_position(math.tan(radians) * self.adjacent - self.offset)    # tan = opposite/adjacent -> tan * adjacent = opposite

    def get_angle(self) -> float:
        """get ramp angle in radians"""
        return math.atan((self.motor.get_position() + self.offset) / self.adjacent)     # like set_angle, just reversed

    def iter_angle(self, radians: float, step_size: float):
        """set angle and yield control after moving a 'step_size' angle"""
        yield from self.motor.iter_position(math.tan(radians) * self.adjacent - self.offset, math.tan(step_size) * self.adjacent)   # translate position and step size from radians to distances
