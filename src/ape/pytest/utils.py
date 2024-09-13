from enum import Enum


class Scope(str, Enum):
    SESSION = "session"
    PACKAGE = "package"
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"

    def __str__(self) -> str:
        return self.value

    @property
    def lower_scopes(self) -> tuple["Scope", ...]:
        if self is Scope.CLASS:
            return (Scope.FUNCTION,)
        elif self is Scope.MODULE:
            return (Scope.CLASS, Scope.FUNCTION)
        elif self is Scope.PACKAGE:
            return (Scope.MODULE, Scope.CLASS, Scope.FUNCTION)
        elif self is Scope.SESSION:
            return (Scope.PACKAGE, Scope.MODULE, Scope.CLASS, Scope.FUNCTION)

        return ()

    @property
    def isolation_fixturename(self) -> str:
        return f"_{self.value}_isolation"
