import sys
import threading
import time
from datetime import datetime, timedelta
from functools import cached_property
from pathlib import Path
from subprocess import run as run_subprocess
from typing import Any

import click
import pytest
from click import Command
from watchdog import events
from watchdog.observers import Observer

from ape.cli.options import ape_cli_context
from ape.logging import LogLevel, _get_level
from ape.utils.basemodel import ManagerAccessMixin as access

# Copied from https://github.com/olzhasar/pytest-watcher/blob/master/pytest_watcher/watcher.py
trigger_lock = threading.Lock()
trigger = None


def emit_trigger():
    """
    Emits trigger to run pytest
    """

    global trigger

    with trigger_lock:
        trigger = datetime.now()


class EventHandler(events.FileSystemEventHandler):
    EVENTS_WATCHED = (
        events.EVENT_TYPE_CREATED,
        events.EVENT_TYPE_DELETED,
        events.EVENT_TYPE_MODIFIED,
        events.EVENT_TYPE_MOVED,
    )

    def dispatch(self, event: events.FileSystemEvent) -> None:
        if event.event_type in self.EVENTS_WATCHED:
            self.process_event(event)

    @cached_property
    def _extensions_to_watch(self) -> list[str]:
        return [".py", *access.compiler_manager.registered_compilers.keys()]

    def _is_path_watched(self, filepath: str) -> bool:
        """
        Check if file should trigger pytest run
        """
        return any(map(filepath.endswith, self._extensions_to_watch))

    def process_event(self, event: events.FileSystemEvent) -> None:
        if self._is_path_watched(event.src_path):
            emit_trigger()


def _run_ape_test(*pytest_args):
    return run_subprocess(["ape", "test", *[f"{a}" for a in pytest_args]])


def _run_main_loop(delay: float, *pytest_args: str) -> None:
    global trigger

    now = datetime.now()
    if trigger and now - trigger > timedelta(seconds=delay):
        _run_ape_test(*pytest_args)

        with trigger_lock:
            trigger = None

    time.sleep(delay)


def _validate_pytest_args(*pytest_args) -> list[str]:
    threshold = len(pytest_args) - 1
    args_iter = iter(pytest_args)
    valid_args = []
    for idx, argument in enumerate(args_iter):
        if idx >= threshold:
            # If the last arg is -v without a value, it is a valid
            # pytest arg.
            valid_args.append(argument)
            break

        elif argument == "-v":
            # Ensure this is a pytest -v and not ape's -v.
            next_arg = next(args_iter)
            lvl_name = _get_level(next_arg)
            if not _is_ape_loglevel(lvl_name):
                valid_args.append(argument)

        else:
            valid_args.append(argument)

    return valid_args


def _is_ape_loglevel(value: Any) -> bool:
    if isinstance(value, (int, LogLevel)):
        return True

    elif isinstance(value, str):
        return (
            value.upper() in [x.name for x in LogLevel]
            or (value.isnumeric() and int(value) in LogLevel)
            or value.lower().startswith("loglevel.")
        )

    return False


class ApeTestCommand(Command):
    def parse_args(self, ctx, args: list[str]) -> list[str]:
        num_args = len(args)
        for idx, argument in enumerate(args):
            if not argument.startswith("-v"):
                continue
            elif (idx == num_args - 1) or argument in ("-vv", "-vvv"):
                # Definitely for pytest.
                ctx.obj["pytest_verbosity"] = argument
                args = [a for a in args if a != argument]
            else:
                # -v with a following arg; ensure not Ape's.
                next_arg = args[idx + 1]
                if not _is_ape_loglevel(next_arg):
                    ctx.obj["pytest_verbosity"] = "-v"
                    args = [a for a in args if a != argument]

        return super().parse_args(ctx, args)


@click.command(
    add_help_option=False,  # NOTE: This allows pass-through to pytest's help
    short_help="Launches pytest and runs the tests for a project",
    context_settings=dict(ignore_unknown_options=True),
    cls=ApeTestCommand,
)
# NOTE: Using '.value' because more performant.
@ape_cli_context(
    default_log_level=LogLevel.WARNING.value,
)
@click.option(
    "-w",
    "--watch",
    is_flag=True,
    default=False,
    help="Watch for changes to project files and re-run the test suite with the given options.",
)
@click.option(
    "--watch-folders",
    multiple=True,
    type=Path,
    default=[Path("contracts"), Path("tests")],
    help=(
        "Folders to watch for changes using `ape test --watch`."
        " Defaults to `contracts/` and `tests/`"
    ),
)
@click.option(
    "--watch-delay",
    type=float,
    default=0.5,
    help="Delay between polling cycles for `ape test --watch`. Defaults to 0.5 seconds.",
)
@click.argument("pytest_args", nargs=-1, type=click.UNPROCESSED)
def cli(cli_ctx, watch, watch_folders, watch_delay, pytest_args):
    pytest_arg_ls = [*pytest_args]
    if pytest_verbosity := cli_ctx.get("pytest_verbosity"):
        pytest_arg_ls.append(pytest_verbosity)

    pytest_arg_ls = _validate_pytest_args(*pytest_arg_ls)
    if watch:
        event_handler = _create_event_handler()
        observer = _create_observer()

        for folder in watch_folders:
            if folder.is_dir():
                observer.schedule(event_handler, folder, recursive=True)
            else:
                cli_ctx.logger.warning(f"Folder '{folder}' doesn't exist or isn't a folder.")

        observer.start()

        try:
            _run_ape_test(*pytest_arg_ls)
            while True:
                _run_main_loop(watch_delay, *pytest_arg_ls)

        finally:
            observer.stop()
            observer.join()

    else:
        return_code = pytest.main([*pytest_arg_ls], ["ape_test"])
        if return_code:
            # only exit with non-zero status to make testing easier
            sys.exit(return_code)


def _create_event_handler():
    # Abstracted for testing purposes.
    return EventHandler()


def _create_observer():
    # Abstracted for testing purposes.
    return Observer()
