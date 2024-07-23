import os
import re
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from fnmatch import fnmatch
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path
from re import Pattern
from tempfile import TemporaryDirectory, gettempdir
from typing import Any, Optional, Union


def is_relative_to(path: Path, target: Path) -> bool:
    """
    Search a path and determine its relevancy.

    Args:
        path (str): Path represents a filesystem to find.
        target (str): Path represents a filesystem to match.

    Returns:
        bool: ``True`` if the path is relative to the target path or ``False``.
    """
    try:
        return target.is_relative_to(path)
    except AttributeError:
        # For Python versions < 3.9
        try:
            target.relative_to(path)
            return True
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

    # Calculate common prefix length
    common_parts = 0
    for target_part, anchor_part in zip(target.parts, anchor.parts):
        if target_part == anchor_part:
            common_parts += 1
        else:
            break

    # Calculate the relative path
    relative_parts = [".."] * (len(anchor.parts) - common_parts) + list(target.parts[common_parts:])
    return Path(*relative_parts)


def get_all_files_in_directory(
    path: Path, pattern: Optional[Union[Pattern, str]] = None, max_files: Optional[int] = None
) -> list[Path]:
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
        max_files (Optional[int]): Optionally set a max file count. This is useful
          because huge file structures will be very slow.

    Returns:
        list[pathlib.Path]: A list of files in the given directory.
    """
    if path.is_file():
        return [path]
    elif not path.is_dir():
        return []

    pattern_obj: Optional[Pattern] = None
    if isinstance(pattern, str):
        pattern_obj = re.compile(pattern)
    elif pattern is not None:
        pattern_obj = pattern

    result: list[Path] = []
    append_result = result.append  # Local variable for faster access
    for file in path.rglob("*.*"):
        if not file.is_file() or (pattern_obj is not None and not pattern_obj.match(file.name)):
            continue

        append_result(file)
        if max_files is not None and len(result) >= max_files:
            break

    return result


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

    def __init__(self, path: Path, exclude: Optional[list[Path]] = None):
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


def get_full_extension(path: Union[Path, str]) -> str:
    """
    For a path like ``Path("Contract.t.sol")``,
    returns ``.t.sol``, unlike the regular Path
    property ``.suffix`` which returns ``.sol``.

    Args:
        path (Path | str): The path with an extension.

    Returns:
        str: The full suffix
    """
    if not path:
        return ""

    path = Path(path)
    if path.is_dir() or path.suffix == "":
        return ""

    name = path.name
    parts = name.split(".")

    if len(parts) > 2 and name.startswith("."):
        return "." + ".".join(parts[2:])
    elif len(parts) > 1:
        return "." + ".".join(parts[1:])

    return ""


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
        name (Optional[str]): Optionally name the temporary directory.

    Returns:
        Any: The result of the function call.
    """
    with create_tempdir(name=name) as temp_dir:
        return fn(temp_dir)


def in_tempdir(path: Path) -> bool:
    """
    Returns ``True`` when the given path is in a temporary directory.

    Args:
        path (Path): The path to check.

    Returns:
        bool
    """
    temp_dir = os.path.normpath(f"{Path(gettempdir()).resolve()}")
    normalized_path = os.path.normpath(path)
    return normalized_path.startswith(temp_dir)


def path_match(path: Union[str, Path], *exclusions: str) -> bool:
    """
    A better glob-matching function. For example:

    >>> from pathlib import Path
    >>> p = Path("test/to/.build/me/2/file.json")
    >>> p.match("**/.build/**")
    False
    >>> from ape.utils.os import path_match
    >>> path_match(p, "**/.build/**")
    True
    """
    path_str = str(path)
    path_path = Path(path)

    for excl in exclusions:
        if fnmatch(path_str, excl):
            return True

        elif fnmatch(path_path.name, excl):
            return True

        else:
            # If the exclusion is he full name of any of the parents
            # (e.g. ".cache", it is a match).
            for parent in path_path.parents:
                if parent.name == excl:
                    return True

                # Walk the path recursively.
                relative_str = path_str.replace(str(parent), "").strip(os.path.sep)
                if fnmatch(relative_str, excl):
                    return True

    return False


def clean_path(path: Path) -> str:
    """
    Replace the home directory with key ``$HOME`` and return
    the path as a str. This is used for outputting paths
    with less doxxing.

    Args:
        path (Path): The path to sanitize.

    Returns:
        str: A sanitized path-str.
    """
    home = Path.home()
    if path.is_relative_to(home):
        return f"$HOME{os.path.sep}{path.relative_to(home)}"

    return f"{path}"


def get_package_path(package_name: str) -> Path:
    """
    Get the path to a package from site-packages.

    Args:
        package_name (str): The name of the package.

    Returns:
        Path
    """
    try:
        dist = distribution(package_name)
    except PackageNotFoundError as err:
        raise ValueError(f"Package '{package_name}' not found in site-packages.") from err

    package_path = Path(str(dist.locate_file(""))) / package_name
    if not package_path.exists():
        raise ValueError(f"Package '{package_name}' not found in site-packages.")

    return package_path
