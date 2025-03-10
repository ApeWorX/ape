import threading
import time
from collections.abc import Iterable
from datetime import datetime, timedelta
from functools import cached_property
from pathlib import Path
from subprocess import run as run_subprocess

from watchdog import events
from watchdog.observers import Observer

from ape.logging import logger

# Copied from https://github.com/olzhasar/pytest-watcher/blob/master/pytest_watcher/watcher.py
trigger_lock = threading.Lock()
trigger = None


def run_with_observer(watch_folders: Iterable[Path], watch_delay: float, *pytest_arg_ls: str):
    event_handler = _create_event_handler()
    observer = _create_observer()

    for folder in watch_folders:
        if folder.is_dir():
            observer.schedule(event_handler, folder, recursive=True)
        else:
            logger.warning(f"Folder '{folder}' doesn't exist or isn't a folder.")

    observer.start()

    try:
        _run_ape_test(*pytest_arg_ls)
        while True:
            _run_main_loop(watch_delay, *pytest_arg_ls)

    finally:
        observer.stop()
        observer.join()


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
        from ape.utils.basemodel import ManagerAccessMixin as access

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


def _create_event_handler():
    # Abstracted for testing purposes.
    return EventHandler()


def _create_observer():
    # Abstracted for testing purposes.
    return Observer()
