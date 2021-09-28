# Inspired / borrowed from the `click-logging` python package.
import logging
import sys
from enum import Enum
from typing import IO

import click


class Level(Enum):
    ERROR = logging.ERROR
    WARNING = logging.WARNING
    INFO = logging.INFO
    SUCCESS = logging.INFO + 1


logging.addLevelName(Level.SUCCESS.value, Level.SUCCESS.name)
logging.SUCCESS = Level.SUCCESS.value  # type: ignore


def success(self, message, *args, **kws):
    """This method gets injecting into python's `logging` module
    to handle logging at this level."""
    if self.isEnabledFor(Level.SUCCESS.value):
        # Yes, logger takes its '*args' as 'args'.
        self._log(Level.SUCCESS.value, message, args, **kws)


logging.Logger.success = success  # type: ignore


CLICK_STYLE_KWARGS = {
    Level.ERROR: dict(fg="bright_red"),
    Level.WARNING: dict(fg="bright_red"),
    Level.INFO: dict(fg="blue"),
    Level.SUCCESS: dict(fg="bright_green"),
}
CLICK_ECHO_KWARGS = {
    Level.ERROR: dict(err=True),
    Level.WARNING: dict(err=True),
    Level.INFO: dict(),
    Level.SUCCESS: dict(),
}


# Borrowed from `click._compat`.
def _isatty(stream: IO) -> bool:
    """Returns ``True`` if the stream is part of tty.
    Borrowed from ``click._compat``."""
    # noinspection PyBroadException
    try:
        return stream.isatty()
    except Exception:
        return False


class ApeColorFormatter(logging.Formatter):
    def __init__(self):
        super().__init__(fmt="%(levelname)s: %(message)s")

    def format(self, record):
        if _isatty(sys.stdout) and _isatty(sys.stderr):
            # only color log messages when sys.stdout and sys.stderr are sent to the terminal
            level = Level(record.levelno)
            styles = CLICK_STYLE_KWARGS.get(level, {})
            record.levelname = click.style(record.levelname, **styles)

        return super().format(record)


class ClickHandler(logging.Handler):
    def __init__(self, echo_kwargs):
        super().__init__()
        self.echo_kwargs = echo_kwargs

    def emit(self, record):
        try:
            msg = self.format(record)
            level = record.levelname.lower()
            if self.echo_kwargs.get(level):
                click.echo(msg, **self.echo_kwargs[level])
            else:
                click.echo(msg)
        except Exception:
            self.handleError(record)


def _get_logger(name) -> logging.Logger:
    """Get a logger with the given ``name`` and configure it for usage with Click."""
    cli_logger = logging.getLogger(name)
    handler = ClickHandler(echo_kwargs=CLICK_ECHO_KWARGS)
    handler.setFormatter(ApeColorFormatter())
    cli_logger.handlers = [handler]
    return cli_logger


logger = _get_logger("ape")


__all__ = ["logger"]
