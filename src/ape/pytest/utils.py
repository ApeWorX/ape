from enum import Enum


class Scope(str, Enum):
    SESSION = "session"
    PACKAGE = "package"
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"

    def __str__(self) -> str:
        return self.value
