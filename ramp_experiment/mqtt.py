#!/usr/bin/python3

"""Module containing objects to communicate with the MQTT Client"""

from struct import Struct
from enum import Enum


ANGLE_STRUCT = Struct("!d")    # angle in radians as 64 bit float

TIMESTAMP_STRUCT = ANGLE_STRUCT     # unix timestamp as 64 bit float

STATUS_STRUCT = Struct("!B")    # status as uint8


class Status(Enum):
    """the status of the experiment"""
    READY = 0       # ready to process targets
    BUSY = 1        # processing target
    ERROR = 2       # landing zone timout expired
    OFFLINE = 3     # server offline or crashed

    @classmethod
    def from_bytes(cls, data: bytes):
        """convert bytes to variant"""
        return cls(STATUS_STRUCT.unpack(data)[0])

    def to_bytes(self) -> bytes:
        """convert variant to bytes"""
        return STATUS_STRUCT.pack(self.value)
