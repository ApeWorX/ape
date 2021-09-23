import logging
import sys
from typing import IO

import click
# Slightly higher than INFO
# Thus, when the default is INFO, you still get SUCCESS.
from click_logging import ClickHandler  # type: ignore

SUCCESS_LOG_LEVEL = logging.INFO + 1
logging.addLevelName(logging.INFO + 1, "SUCCESS")
logging.SUCCESS = SUCCESS_LOG_LEVEL  # type: ignore


def success(self, message, *args, **kws):
    """This method gets injecting into python's `logging` module
    to handle logging at this level."""
    if self.isEnabledFor(SUCCESS_LOG_LEVEL):
        # Yes, logger takes its '*args' as 'args'.
        self._log(SUCCESS_LOG_LEVEL, message, args, **kws)


logging.Logger.success = success  # type: ignore


CLICK_STYLE_KWARGS = {
    "EXCEPTION": dict(fg="bright_red"),
    "CRITICAL": dict(fg="bright_red"),
    "ERROR": dict(fg="bright_red"),
    "WARNING": dict(fg="bright_red"),
    "INFO": dict(fg="blue"),
    "DEBUG": dict(fg="blue"),
    "SUCCESS": dict(fg="bright_green"),
}
CLICK_ECHO_KWARGS = {
    "EXCEPTION": dict(err=True),
    "CRITICAL": dict(err=True),
    "ERROR": dict(err=True),
    "WARNING": dict(err=True),
    "INFO": dict(),
    "DEBUG": dict(),
    "SUCCESS": dict(),
}


# Borrowed from `click._compat`.
def _isatty(stream: IO) -> bool:
    """Returns ``True`` if the stream is part of tty.
    Borrowed from ``click._compat``."""
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
            record.levelname = click.style(record.levelname, **CLICK_STYLE_KWARGS[record.levelname])

        return super().format(record)


def _get_logger(name) -> logging.Logger:
    """Get a logger with the given ``name`` and configure it for usage with Click."""
    _logger = logging.getLogger(name)
    handler = ClickHandler(echo_kwargs=CLICK_ECHO_KWARGS)
    handler.setFormatter(ApeColorFormatter())
    _logger.handlers = [handler]
    return _logger


logger = _get_logger("ape")


__all__ = ["logger"]
