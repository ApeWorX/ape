from typing import Optional

import click

from ape.logging import logger


class Abort(click.ClickException):
    """
    A wrapper around a CLI exception. When you raise this error,
    the error is nicely printed to the terminal. This is
    useful for all user-facing errors.
    """

    def __init__(self, message: Optional[str] = None):
        message = message or "Operation aborted."
        super().__init__(message)

    def show(self, file=None):
        """
        Override default ``show`` to print CLI errors in red text.
        """

        logger.error(self.format_message())
