# Inspired / borrowed from the `click-logging` python package.
import logging
import sys
from enum import Enum
from typing import IO

import click


class LogLevel(Enum):
    ERROR = logging.ERROR
    WARNING = logging.WARNING
    INFO = logging.INFO
    SUCCESS = logging.INFO + 1


logging.addLevelName(LogLevel.SUCCESS.value, LogLevel.SUCCESS.name)
logging.SUCCESS = LogLevel.SUCCESS.value  # type: ignore


def success(self, message, *args, **kws):
    """This method gets injecting into python's `logging` module
    to handle logging at this level."""
    if self.isEnabledFor(LogLevel.SUCCESS.value):
        # Yes, logger takes its '*args' as 'args'.
        self._log(LogLevel.SUCCESS.value, message, args, **kws)


logging.Logger.success = success  # type: ignore


CLICK_STYLE_KWARGS = {
    LogLevel.ERROR: dict(fg="bright_red"),
    LogLevel.WARNING: dict(fg="bright_red"),
    LogLevel.INFO: dict(fg="blue"),
    LogLevel.SUCCESS: dict(fg="bright_green"),
}
CLICK_ECHO_KWARGS = {
    LogLevel.ERROR: dict(err=True),
    LogLevel.WARNING: dict(err=True),
    LogLevel.INFO: dict(),
    LogLevel.SUCCESS: dict(),
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
            level = LogLevel(record.levelno)
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
