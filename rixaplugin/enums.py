from enum import Flag, auto, IntFlag, Enum
from typing import Any


class AutoNumber(IntFlag):
    def _generate_next_value_(name: str, start: int, count: int, last_values: list[Any]) -> int:
        return 1 << count


class HeaderFlags(AutoNumber):
    NONE = 0
    ACKNOWLEDGE = auto()
    SERVER = auto()
    CLIENT = auto()
    FUNCTION_CALL = auto()
    FUNCTION_RETURN = auto()
    EXCEPTION_RETURN = auto()
    TIME_ESTIMATE_AND_ACKNOWLEDGEMENT = auto()
    LOG = auto()
    FUNCTION_NOT_FOUND = auto()
    API_CALL = auto()


class CallstackType(AutoNumber):
    WITHOUT_PLUGIN = 0
    LOCAL = auto()
    NETWORK = auto()
    ASYNCIO = auto()
    THREAD = auto()
    PROCESS = auto()


class Scope(AutoNumber):
    USER = auto()
    LOCAL = auto()
    SERVER = auto()
