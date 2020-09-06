#!/usr/bin/python3

# run demo (dont forget to set the pins 3, 2 to GPIO mode and enable PWM)
import math
from onionGpio import OnionGpio, Value, Direction, Edge
from onionPwm import OnionPwm
from .A4988 import A4988
from .motor import WormMotor
from .ramp import Ramp


driver = A4988(0, 1, 3, 2)
motor = WormMotor(driver, Value.LOW, 0.025, 200, 0, 80)     # low pps = more power
with OnionGpio(11) as landing_zone, OnionPwm(0, 0) as elevator, Ramp(motor, 107, offset=0.05235) as ramp:  # ramp has a 3° angle in normal position
    landing_zone.setDirection(Direction.INPUT)
    landing_zone.setEdge(Edge.FALLING)
    elevator.set_frequency(2000)
    elevator.set_duty_cycle(100)    # 100% power
    print("Enter angles")
    while True:
        ramp.set_angle(math.radians(float(input(">>> "))))
        print("ramp angle: {0}".format(math.degrees(ramp.get_angle())))
        elevator.enable()
        try:
            landing_zone.waitForEdge(30)
        except TimeoutError:
            print("Error: marble left the ramp")
        else:
            print("marble landed")
        finally:
            elevator.disable()
print("End")
