import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Sequence

import click
import pytest
from watchdog import events
from watchdog.observers import Observer

from ape.cli import ape_cli_context
from ape.utils import ManagerAccessMixin, cached_property

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


class EventHandler(events.FileSystemEventHandler, ManagerAccessMixin):
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
    def _extensions_to_watch(self) -> List[str]:
        return [".py", *self.compiler_manager.registered_compilers.keys()]

    def _is_path_watched(self, filepath: str) -> bool:
        """
        Check if file should trigger pytest run
        """
        return any(map(filepath.endswith, self._extensions_to_watch))

    def process_event(self, event: events.FileSystemEvent) -> None:
        if self._is_path_watched(event.src_path):
            emit_trigger()


def _run_ape_test(pytest_args):
    return subprocess.run(["ape", "test", *pytest_args])


def _run_main_loop(delay: float, pytest_args: Sequence[str]) -> None:
    global trigger

    now = datetime.now()
    if trigger and now - trigger > timedelta(seconds=delay):
        _run_ape_test(pytest_args)

        with trigger_lock:
            trigger = None

    time.sleep(delay)


@click.command(
    add_help_option=False,  # NOTE: This allows pass-through to pytest's help
    short_help="Launches pytest and runs the tests for a project",
    context_settings=dict(ignore_unknown_options=True),
)
@ape_cli_context()
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
    if watch:
        event_handler = EventHandler()

        observer = Observer()

        for folder in watch_folders:
            if folder.is_dir():
                observer.schedule(event_handler, folder, recursive=True)

            else:
                cli_ctx.logger.warning(f"Folder '{folder}' doesn't exist or isn't a folder.")

        observer.start()

        try:
            _run_ape_test(pytest_args)

            while True:
                _run_main_loop(watch_delay, pytest_args)

        finally:
            observer.stop()
            observer.join()

    else:
        return_code = pytest.main([*pytest_args], ["ape_test"])
        if return_code:
            # only exit with non-zero status to make testing easier
            sys.exit(return_code)
