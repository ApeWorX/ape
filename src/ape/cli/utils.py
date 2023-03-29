import traceback
from inspect import getframeinfo, stack
from pathlib import Path
from typing import Optional

import click

from ape.exceptions import ApeException
from ape.logging import LogLevel, logger


class Abort(click.ClickException):
    """
    A wrapper around a CLI exception. When you raise this error,
    the error is nicely printed to the terminal. This is
    useful for all user-facing errors.
    """

    def __init__(self, message: Optional[str] = None):
        if not message:
            caller = getframeinfo(stack()[1][0])
            file_path = Path(caller.filename)
            location = file_path.name if file_path.is_file() else caller.filename
            message = f"Operation aborted in {location}::{caller.function} on line {caller.lineno}."

        super().__init__(message)

    def show(self, file=None):
        """
        Override default ``show`` to print CLI errors in red text.
        """

        logger.error(self.format_message())


def abort(err: ApeException, show_traceback: Optional[bool] = None) -> Abort:
    show_traceback = (
        logger.level == LogLevel.DEBUG.value if show_traceback is None else show_traceback
    )
    if show_traceback:
        tb = traceback.format_exc()
        err_message = tb or str(err)
    else:
        err_message = str(err)

    return Abort(f"({type(err).__name__}) {err_message}")
