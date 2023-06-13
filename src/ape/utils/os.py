import os
import re
import sys
from pathlib import Path
from typing import List, Optional, Pattern, Union


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
    Returns all the files in a directory structure.

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
    if not path.exists():
        return []

    elif path.is_file():
        return [path]

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
