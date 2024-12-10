from enum import Enum


class Scope(int, Enum):
    SESSION = 0
    PACKAGE = 1
    MODULE = 2
    CLASS = 3
    FUNCTION = 4

    def __str__(self) -> str:
        return self.name.lower()

    @property
    def isolation_fixturename(self) -> str:
        return f"_{self}_isolation"
