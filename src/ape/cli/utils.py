import click

from ape.logging import logger


class Abort(click.ClickException):
    """Wrapper around a CLI exception"""

    def show(self, file=None):
        """Override default ``show`` to print CLI errors in red text."""
        logger.error(self.format_message())
