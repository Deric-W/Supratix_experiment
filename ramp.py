#!/usr/bin/python3

"""Module for controlling the ramp"""

import math

class Ramp:
    def __init__(self, motor, base):
        """init with motor object and the length of the base of the ramp"""
        self.motor = motor
        self.base = base
    
    def __enter__(self):
        return self
    
    def __exit__(self, type, value, traceback):
        self.shutdown()
        return False    # we dont handle exceptions
    
    def shutdown(self):
        """shutdown ramp motor"""
        self.motor.shutdown()

    def set_angle(self, radians):
        """set ramp angle in radians"""
        self.motor.set_position(math.tan(radians) * self.base)

    def get_angle(self):
        """get ramp angle in radians"""
        return math.atan(self.motor.get_position() / self.base)
