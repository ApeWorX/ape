import os
import re
import sys
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable, Iterator, List, Optional, Pattern, Union


def is_relative_to(path: Path, target: Path) -> bool:
    """
    Search a path and determine its relevancy.

    Args:
        path (str): Path represents a filesystem to find.
        target (str): Path represents a filesystem to match.

    Returns:
        bool: ``True`` if the path is relative to the target path or ``False``.
    """
    if hasattr(path, "is_relative_to"):
        # NOTE: Only available ``>=3.9``
        return target.is_relative_to(path)  # type: ignore

    else:
        try:
            return target.relative_to(path) is not None
        except ValueError:
            return False


def get_relative_path(target: Path, anchor: Path) -> Path:
    """
    Compute the relative path of ``target`` relative to ``anchor``,
    which may or may not share a common ancestor.

    **NOTE**: Both paths must be absolute.

    Args:
        target (pathlib.Path): The path we are interested in.
        anchor (pathlib.Path): The path we are starting from.

    Returns:
        pathlib.Path: The new path to the target path from the anchor path.
    """
    if not target.is_absolute():
        raise ValueError("'target' must be an absolute path.")
    if not anchor.is_absolute():
        raise ValueError("'anchor' must be an absolute path.")

    anchor_copy = Path(str(anchor))
    levels_deep = 0
    while not is_relative_to(anchor_copy, target):
        levels_deep += 1
        anchor_copy = anchor_copy.parent

    return Path("/".join(".." for _ in range(levels_deep))).joinpath(
        str(target.relative_to(anchor_copy))
    )


def get_all_files_in_directory(
    path: Path, pattern: Optional[Union[Pattern, str]] = None
) -> List[Path]:
    """
    Returns all the files in a directory structure (recursive).

    For example, given a directory structure like::

        dir_a: dir_b, file_a, file_b
        dir_b: file_c

    and you provide the path to ``dir_a``, it will return a list containing
    the paths to ``file_a``, ``file_b`` and ``file_c``.

    Args:
        path (pathlib.Path): A directory containing files of interest.
        pattern (Optional[Union[Pattern, str]]): Optionally provide a regex
          pattern to match.

    Returns:
        List[pathlib.Path]: A list of files in the given directory.
    """
    if path.is_file():
        return [path]
    elif not path.is_dir():
        return []

    # is dir
    all_files = [p for p in list(path.rglob("*.*")) if p.is_file()]
    if pattern:
        if isinstance(pattern, str):
            pattern = re.compile(pattern)

        return [f for f in all_files if pattern.match(f.name)]

    return all_files


def expand_environment_variables(contents: str) -> str:
    """
    Replace substrings of the form ``$name`` or ``${name}`` in the given path
    with the value of environment variable name.

    Args:
        contents (str): A path-like object representing a file system.
                            A path-like object is either a string or bytes object
                            representing a path.
    Returns:
        str: The given content with all environment variables replaced with their values.
    """
    return os.path.expandvars(contents)


class use_temp_sys_path:
    """
    A context manager to manage injecting and removing paths from
    a user's sys paths without permanently modifying it.
    """

    def __init__(self, path: Path, exclude: Optional[List[Path]] = None):
        self.temp_path = str(path)
        self.exclude = [str(p) for p in exclude or []]

    def __enter__(self):
        for path in self.exclude:
            if path in sys.path:
                sys.path.remove(path)
            else:
                # Preventing trying to re-add during exit.
                self.exclude.remove(path)

        if self.temp_path not in sys.path:
            sys.path.append(self.temp_path)

    def __exit__(self, *exc):
        if self.temp_path in sys.path:
            sys.path.remove(self.temp_path)

        for path in self.exclude:
            if path not in sys.path:
                sys.path.append(path)


def get_full_extension(path: Path) -> str:
    """
    For a path like ``Path("Contract.t.sol")``,
    returns ``.t.sol``, unlike the regular Path
    property ``.suffix`` which returns ``.sol``.
    """
    if path.is_dir():
        return ""

    parts = path.name.split(".")
    start_idx = 2 if path.name.startswith(".") else 1

    # NOTE: Handles when given just `.hiddenFile` since slice indices
    #   may exceed their bounds.
    suffix = ".".join(parts[start_idx:])

    return f".{suffix}" if suffix and f".{suffix}" != f"{path.name}" else ""


@contextmanager
def create_tempdir(name: Optional[str] = None) -> Iterator[Path]:
    """
    Create a temporary directory. Differs from ``TemporaryDirectory()``
    context-call alone because it automatically resolves the path.

    Args:
        name (Optional[str]): Optional provide a name of  the directory.
          Else, defaults to root of ``tempfile.TemporaryDirectory()``
          (resolved).

    Returns:
        Iterator[Path]: Context managing the temporary directory.
    """
    with TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir).resolve()

        if name:
            path = temp_path / name
            path.mkdir()
        else:
            path = temp_path

        yield path


def run_in_tempdir(
    fn: Callable[
        [
            Path,
        ],
        Any,
    ],
    name: Optional[str] = None,
):
    """
    Run the given function in a temporary directory with its path
    resolved.

    Args:
        fn (Callable): A function that takes a path. It gets called
          with the resolved path to the temporary directory.

    Returns:
        Any: The result of the function call.
    """
    with create_tempdir(name=name) as temp_dir:
        return fn(temp_dir)
