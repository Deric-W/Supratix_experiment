#!/usr/bin/python3

# run demo
import math
from .A4988 import A4988
from .motor import WormMotor
from .ramp import Ramp

driver = A4988(0, 1, 19, 18)
motor = WormMotor(driver, 0, 0.025, 1000, 0, 82)
with Ramp(motor, 70) as ramp:
    print("Enter angles")
    while True:
        ramp.set_angle(math.radians(int(input(">>> "))))
        print(math.degrees(ramp.get_angle()))
print("End")
