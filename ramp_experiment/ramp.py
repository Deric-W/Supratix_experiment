#!/usr/bin/python3

"""Module for controlling the ramp"""

import math

class Ramp:
    def __init__(self, motor, base: float, offset: float=0):
        """init with motor object, the length of the base of the ramp and a angle offset in radians"""
        self.motor = motor
        self.base = base
        self.offset = offset
    
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
        self.motor.set_position(math.tan(radians - self.offset) * self.base)

    def get_angle(self) -> float:
        """get ramp angle in radians"""
        return math.atan(self.motor.get_position() / self.base) + self.offset
    
    def iter_angle(self, radians: float, step_size: int):
        """set angle step by step"""
        yield from self.motor.iter_position(math.tan(radians - self.offset) * self.base, math.tan(step_size) * self.base)
