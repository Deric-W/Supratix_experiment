#!/usr/bin/python3

# run demo (dont forget to set the pins 3 and 2 to GPIO mode and enable PWM)
from math import radians, degrees
from onionGpio import OnionGpio, Value, Direction, Edge
from onionPwm import OnionPwm
from .A4988 import A4988
from .motor import WormMotor
from .ramp import Ramp


driver = A4988(0, 1, 3, 2)
motor = WormMotor(driver, Value.LOW, 0.025, 200, 0, 80)     # low pps = more power
with OnionGpio(11) as landing_zone, OnionPwm(0, 0) as elevator, Ramp(motor, 107, offset=0.06528) as ramp:  # ramp has a 3.74° angle in normal position
    landing_zone.setDirection(Direction.INPUT)
    landing_zone.setEdge(Edge.FALLING)  # prepare for edge
    elevator.set_frequency(2000)
    elevator.set_duty_cycle(100)    # 100% power
    print("Enter angles")
    while True:
        ramp.set_angle(radians(float(input(">>> "))))   # nosec
        print("ramp angle: {0:>5.2f}".format(degrees(ramp.get_angle())))    # display as fixed point number with a precision of 2
        elevator.enable()   # transport marble to the top of the ramp
        try:
            landing_zone.waitForEdge(30)    # wait for arrival of the marble
        except TimeoutError:        # received no edge -> marble left the experiment
            print("Error: marble left the ramp")
        else:                       # received an edge -> marble landed
            print("marble landed")
        finally:            # make sure to disable the elevator after the experiment no matter what happens
            elevator.disable()
print("End")
