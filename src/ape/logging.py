# Inspired / borrowed from the `click-logging` python package.
import logging
import sys
import traceback
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from enum import IntEnum
from pathlib import Path
from typing import IO, Any, Optional, Union

import click
from rich.console import Console as RichConsole
from yarl import URL


class LogLevel(IntEnum):
    ERROR = logging.ERROR
    WARNING = logging.WARNING
    SUCCESS = logging.INFO + 1
    INFO = logging.INFO
    DEBUG = logging.DEBUG


logging.addLevelName(LogLevel.SUCCESS.value, LogLevel.SUCCESS.name)
logging.SUCCESS = LogLevel.SUCCESS.value  # type: ignore
DEFAULT_LOG_LEVEL = LogLevel.INFO.name
DEFAULT_LOG_FORMAT = "%(levelname_semicolon_padded)s %(plugin)s %(message)s"
HIDDEN_MESSAGE = "[hidden]"


def success(self, message, *args, **kws):
    """This method gets injected into python's `logging` module
    to handle logging at this level."""

    if self.isEnabledFor(LogLevel.SUCCESS.value):
        # Yes, logger takes its '*args' as 'args'.
        self._log(LogLevel.SUCCESS.value, message, args, **kws)


logging.Logger.success = success  # type: ignore


CLICK_STYLE_KWARGS = {
    LogLevel.ERROR: dict(fg="bright_red"),
    LogLevel.WARNING: dict(fg="bright_yellow"),
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
    """Returns ``True`` if the stream is part of a tty.
    Borrowed from ``click._compat``."""
    # noinspection PyBroadException
    try:
        return stream.isatty()
    except Exception:
        return False


class ApeColorFormatter(logging.Formatter):
    def __init__(self, fmt: Optional[str] = None):
        fmt = fmt or DEFAULT_LOG_FORMAT
        super().__init__(fmt=fmt)

    def format(self, record):
        record.levelname_semicolon_padded = f"{record.levelname}:".ljust(8)
        if _isatty(sys.stdout) and _isatty(sys.stderr):
            # Only color log messages when sys.stdout and sys.stderr are sent to the terminal.
            level = LogLevel(record.levelno)
            default_dict: dict[str, Any] = {}
            styles: dict[str, Any] = CLICK_STYLE_KWARGS.get(level, default_dict)
            record.levelname = click.style(record.levelname, **styles)
            record.levelname_semicolon_padded = click.style(
                record.levelname_semicolon_padded, **styles
            )

        path = Path(record.pathname)
        record.plugin = ""
        for part in path.parts:
            if part.startswith("ape-"):
                record.plugin = f" ({part})"
                break

        return super().format(record)


class ClickHandler(logging.Handler):
    def __init__(
        self, echo_kwargs: dict, handlers: Optional[Sequence[Callable[[str], str]]] = None
    ):
        super().__init__()
        self.echo_kwargs = echo_kwargs
        self.handlers = handlers or []

    def emit(self, record):
        try:
            msg = self.format(record)
            for handler in self.handlers:
                msg = handler(msg)

            level = record.levelname.lower()
            if self.echo_kwargs.get(level):
                click.echo(msg, **self.echo_kwargs[level])
            else:
                click.echo(msg)
        except Exception:
            self.handleError(record)


class ApeLogger:
    _mentioned_verbosity_option = False
    _extra_loggers: dict[str, logging.Logger] = {}

    def __init__(
        self,
        _logger: logging.Logger,
        fmt: str,
    ):
        self.error = _logger.error
        self.warning = _logger.warning
        self.success = getattr(_logger, "success", _logger.info)
        self.info = _logger.info
        self.debug = _logger.debug
        self._logger = _logger
        self._did_parse_sys_argv = False
        self._load_from_sys_argv()
        self.fmt = fmt

    @classmethod
    def create(cls, fmt: Optional[str] = None) -> "ApeLogger":
        fmt = fmt or DEFAULT_LOG_FORMAT
        _logger = get_logger("ape", fmt=fmt)
        return cls(_logger, fmt)

    def format(self, fmt: Optional[str] = None):
        self.fmt = fmt or DEFAULT_LOG_FORMAT
        fmt = fmt or DEFAULT_LOG_FORMAT
        _format_logger(self._logger, fmt)

    def _load_from_sys_argv(self, default: Optional[Union[str, int, LogLevel]] = None):
        """
        Load from sys.argv to beat race condition with `click`.
        """
        if self._did_parse_sys_argv:
            # Already parsed.
            return

        log_level = _get_level(level=default)
        level_names = [lvl.name for lvl in LogLevel]

        #  Minus 2 because if `-v` is the last arg, it is not our verbosity `-v`.
        num_args = len(sys.argv) - 2

        for arg_i in range(1, 1 + num_args):
            if sys.argv[arg_i] == "-v" or sys.argv[arg_i] == "--verbosity":
                try:
                    level = _get_level(sys.argv[arg_i + 1].upper())
                except Exception:
                    # Let it fail in a better spot, or is not our level.
                    continue

                if level in level_names:
                    self._sys_argv = level
                    log_level = level
                    break
                else:
                    # Not our level.
                    continue

        self.set_level(log_level)
        self._did_parse_sys_argv = True

    @property
    def level(self) -> int:
        return self._logger.level

    def set_level(self, level: Union[str, int, LogLevel]):
        """
        Change the global ape logger log-level.

        Args:
            level (str): The name of the level or the value of the log-level.
        """
        if level == self._logger.level:
            return
        elif isinstance(level, LogLevel):
            level = level.value
        elif isinstance(level, str) and level.lower().startswith("loglevel."):
            # Seen in some environments.
            level = level.split(".")[-1].strip()

        self._logger.setLevel(level)
        for _logger in self._extra_loggers.values():
            _logger.setLevel(level)

    @contextmanager
    def at_level(self, level: Union[str, int, LogLevel]) -> Iterator:
        """
        Change the log-level in a context.

        Args:
            level (Union[str, int, LogLevel]): The level to use.

        Returns:
            Iterator
        """

        initial_level = self.level
        self.set_level(level)
        yield
        self.set_level(initial_level)

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
        self.log_debug_stack_trace()

    def error_from_exception(self, err: Exception, message: str):
        """
        Log an error to the user with the given message,
        log the stack-trace of the error at the DEBUG level, and
        mention how to enable DEBUG logging (only once).
        """
        message = self._create_message_from_error(err, message)
        self._logger.error(message)
        self.log_debug_stack_trace()

    def _create_message_from_error(self, err: Exception, message: str):
        err_type_name = getattr(type(err), "__name__", "Exception")
        err_output = f"{err_type_name}: {err}"
        message = f"{message}\n\t{err_output}"
        if not self._mentioned_verbosity_option:
            message += "\n\t(Use `--verbosity DEBUG` to see full stack-trace)"
            self._mentioned_verbosity_option = True

        return message

    def log_debug_stack_trace(self):
        stack_trace = traceback.format_exc()
        self._logger.debug(stack_trace)

    def create_logger(
        self, new_name: str, handlers: Optional[Sequence[Callable[[str], str]]] = None
    ) -> logging.Logger:
        _logger = get_logger(new_name, fmt=self.fmt, handlers=handlers)
        _logger.setLevel(self.level)
        self._extra_loggers[new_name] = _logger
        return _logger


def _format_logger(
    _logger: logging.Logger, fmt: str, handlers: Optional[Sequence[Callable[[str], str]]] = None
):
    handler = ClickHandler(echo_kwargs=CLICK_ECHO_KWARGS, handlers=handlers)
    formatter = ApeColorFormatter(fmt=fmt)
    handler.setFormatter(formatter)

    # Remove existing handler(s)
    for existing_handler in _logger.handlers[:]:
        if isinstance(existing_handler, ClickHandler):
            _logger.removeHandler(existing_handler)

    _logger.addHandler(handler)


def get_logger(
    name: str, fmt: Optional[str] = None, handlers: Optional[Sequence[Callable[[str], str]]] = None
) -> logging.Logger:
    """
    Get a logger with the given ``name`` and configure it for usage with Ape.

    Args:
        name (str): The name of the logger.
        fmt (Optional[str]): The format of the logger. Defaults to the Ape
          logger's default format: ``"%(levelname)s%(plugin)s: %(message)s"``.
        handlers (Optional[Sequence[Callable[[str], str]]]): Additional log message handlers.

    Returns:
        ``logging.Logger``
    """
    _logger = logging.getLogger(name)
    _format_logger(_logger, fmt=fmt or DEFAULT_LOG_FORMAT, handlers=handlers)
    return _logger


def _get_level(level: Optional[Union[str, int, LogLevel]] = None) -> str:
    if level is None:
        return DEFAULT_LOG_LEVEL
    elif isinstance(level, LogLevel):
        return level.name
    elif isinstance(level, int) or (isinstance(level, str) and level.isnumeric()):
        return LogLevel(int(level)).name
    elif isinstance(level, str) and level.lower().startswith("loglevel."):
        # Handle 'LogLevel.' prefix.
        return level.split(".")[-1].strip()

    return level


def sanitize_url(url: str) -> str:
    """Removes sensitive information from given URL"""

    url_obj = URL(url).with_user(None).with_password(None)

    # If there is a path, hide it but show that you are hiding it.
    # Use string interpolation to prevent URL-character encoding.
    return f"{url_obj.with_path('')}/{HIDDEN_MESSAGE}" if url_obj.path else f"{url}"


logger = ApeLogger.create()


class _RichConsoleFactory:
    rich_console_map: dict[str, RichConsole] = {}

    def get_console(self, file: Optional[IO[str]] = None, **kwargs) -> RichConsole:
        # Configure custom file console
        file_id = str(file)
        if file_id not in self.rich_console_map:
            self.rich_console_map[file_id] = RichConsole(file=file, width=100, **kwargs)

        return self.rich_console_map[file_id]


_factory = _RichConsoleFactory()


def get_rich_console(file: Optional[IO[str]] = None, **kwargs) -> RichConsole:
    """
    Get an Ape-configured rich console.

    Args:
        file (Optional[IO[str]]): The file to output to. Will default
          to using stdout.

    Returns:
        ``rich.Console``.
    """
    return _factory.get_console(file)


__all__ = ["DEFAULT_LOG_LEVEL", "logger", "LogLevel", "ApeLogger", "get_rich_console"]
