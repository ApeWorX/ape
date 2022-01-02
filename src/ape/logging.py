# Inspired / borrowed from the `click-logging` python package.
import logging
import sys
import traceback
from enum import Enum
from typing import IO

import click


class LogLevel(Enum):
    ERROR = logging.ERROR
    WARNING = logging.WARNING
    SUCCESS = logging.INFO + 1
    INFO = logging.INFO
    DEBUG = logging.DEBUG


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
    LogLevel.SUCCESS: dict(fg="bright_green"),
    LogLevel.INFO: dict(fg="blue"),
    LogLevel.DEBUG: dict(fg="blue"),
}
CLICK_ECHO_KWARGS = {
    LogLevel.ERROR: dict(err=True),
    LogLevel.WARNING: dict(err=True),
    LogLevel.SUCCESS: dict(),
    LogLevel.INFO: dict(),
    LogLevel.DEBUG: dict(),
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


class CliLogger:
    _mentioned_verbosity_option = False

    def __init__(self):
        _logger = _get_logger("ape")
        self.error = _logger.error
        self.warning = _logger.warning
        self.success = _logger.success  # type: ignore
        self.info = _logger.info
        self.debug = _logger.debug
        self._logger = _logger
        self._web3_request_manager_logger = _get_logger("web3.RequestManager")
        self._web3_http_provider_logger = _get_logger("web3.providers.HTTPProvider")

    @property
    def level(self) -> int:
        return self._logger.level

    def set_level(self, level_name: str):
        self._logger.setLevel(level_name)
        self._web3_request_manager_logger.setLevel(level_name)
        self._web3_http_provider_logger.setLevel(level_name)

    def log_error(self, err: Exception):
        """
        Avoids logging empty messages.
        """
        message = str(err)
        if message:
            self._logger.error(message)

    def warn_from_exception(self, err: Exception, message: str):
        """
        Warn the user with the given message,
        log the stack-trace of the error at the DEBUG level, and
        mention how to enable DEBUG logging (only once).
        """
        message = self._create_message_from_error(err, message)
        self._logger.warning(message)
        self._log_debug_stack_trace()

    def error_from_exception(self, err: Exception, message: str):
        """
        Log an error to the user with the given message,
        log the stack-trace of the error at the DEBUG level, and
        mention how to enable DEBUG logging (only once).
        """
        message = self._create_message_from_error(err, message)
        self._logger.error(message)
        self._log_debug_stack_trace()

    def _create_message_from_error(self, err: Exception, message: str):
        err_output = f"{type(err).__name__}: {err}"
        message = f"{message}\n\t{err_output}"
        if not self._mentioned_verbosity_option:
            message += "\n\t(Use `--verbosity DEBUG` to see full stack-trace)"
            self._mentioned_verbosity_option = True

        return message

    def _log_debug_stack_trace(self):
        stack_trace = traceback.format_exc()
        self._logger.debug(stack_trace)


def _get_logger(name: str) -> logging.Logger:
    """Get a logger with the given ``name`` and configure it for usage with Click."""
    cli_logger = logging.getLogger(name)
    handler = ClickHandler(echo_kwargs=CLICK_ECHO_KWARGS)
    handler.setFormatter(ApeColorFormatter())
    cli_logger.handlers = [handler]
    return cli_logger


logger = CliLogger()


__all__ = ["logger", "LogLevel"]
