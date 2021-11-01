import click

from ape.logging import logger


class Abort(click.ClickException):
    """Wrapper around a CLI exception"""

    def __init__(self, message):
        if not message.endswith("."):
            message = f"{message}."

        super().__init__(message)

    def show(self, file=None):
        """Override default ``show`` to print CLI errors in red text."""
        logger.error(self.format_message())
