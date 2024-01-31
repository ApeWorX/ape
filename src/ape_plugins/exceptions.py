from typing import Optional

from ape.exceptions import ApeException


class PluginInstallError(ApeException):
    """
    An error to use when installing a plugin fails.
    """


class PluginVersionError(PluginInstallError):
    """
    An error related to specified plugin version.
    """

    def __init__(
        self, operation: str, reason: Optional[str] = None, resolution: Optional[str] = None
    ):
        message = f"Unable to {operation} plugin."
        if reason:
            message = f"{message}\nReason: {reason}"
        if resolution:
            message = f"{message}\nTo resolve: {resolution}"

        super().__init__(message)
