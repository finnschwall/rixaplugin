from enum import Flag, auto, IntFlag, Enum
from typing import Any


class AutoNumber(IntFlag):
    def _generate_next_value_(name: str, start: int, count: int, last_values: list[Any]) -> int:
        return 1 << count

    def __str__(self):
        if self == AutoNumber(0):
            return self.name  # Direct match, return the name
        members = [member.name for member in self.__class__ if member in self and member.value != 0]
        return '|'.join(members)
        # return str(self.name)

    def __repr__(self):
        if self == AutoNumber(0):
            return self.name  # Direct match, return the name
        members = [member.name for member in self.__class__ if member in self and member.value != 0]
        return '|'.join(members)
        # return str(self.name)

class FunctionPointerType(AutoNumber):
    NONE = 0
    LOCAL = auto()
    REMOTE = auto()
    # both are remote, but lookup is different
    SERVER = auto()
    CLIENT = auto()

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
