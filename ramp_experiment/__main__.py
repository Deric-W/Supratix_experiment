#!/usr/bin/python3

# run demo
import math
from onionGpio import Value
from .A4988 import A4988
from .motor import WormMotor
from .ramp import Ramp

driver = A4988(0, 1, 19, 18)
motor = WormMotor(driver, Value.LOW, 0.025, 600, 0, 80)
with Ramp(motor, 107, offset=0.05235) as ramp:
    print("Enter angles")
    while True:
        ramp.set_angle(math.radians(float(input(">>> "))))
        print(math.degrees(ramp.get_angle()))
print("End")
