import collections
import json
import os
from copy import deepcopy
from functools import lru_cache
from hashlib import md5
from pathlib import Path
from typing import Any, Dict

import click
import yaml
from importlib_metadata import PackageNotFoundError, packages_distributions, version

try:
    from functools import cached_property
except ImportError:
    from backports.cached_property import cached_property  # type: ignore

try:
    from functools import singledispatchmethod
except ImportError:
    from singledispatchmethod import singledispatchmethod  # type: ignore


@lru_cache(maxsize=None)
def get_distributions():
    return packages_distributions()


def is_relative_to(path: Path, target: Path) -> bool:
    if hasattr(path, "is_relative_to"):
        # NOTE: Only available `>=3.9`
        return target.is_relative_to(path)  # type: ignore

    else:
        try:
            return target.relative_to(path) is not None
        except ValueError:
            return False


def get_relative_path(target: Path, anchor: Path) -> Path:
    """
    Compute the relative path of `target` relative to `anchor`,
    which may or may not share a common ancestor.
    NOTE: Both paths must be absolute
    """
    assert anchor.is_absolute()
    assert target.is_absolute()

    anchor_copy = Path(str(anchor))
    levels_deep = 0
    while not is_relative_to(anchor_copy, target):
        levels_deep += 1
        assert anchor_copy != anchor_copy.parent
        anchor_copy = anchor_copy.parent

    return Path("/".join(".." for _ in range(levels_deep))).joinpath(
        str(target.relative_to(anchor_copy))
    )


def get_package_version(obj: Any) -> str:
    # If value is already cached/static
    if hasattr(obj, "__version__"):
        return obj.__version__

    # NOTE: In case were don't pass a module name
    if not isinstance(obj, str):
        obj = obj.__name__

    # Reduce module string to base package
    # NOTE: Assumed that string input is module name e.g. `__name__`
    pkg_name = obj.split(".")[0]

    # NOTE: In case the distribution and package name differ
    dists = get_distributions()
    if pkg_name in dists:
        # NOTE: Shouldn't really be more than 1, but never know
        assert len(dists[pkg_name]) == 1
        pkg_name = dists[pkg_name][0]

    try:
        return version(pkg_name)

    except PackageNotFoundError:
        # NOTE: Must handle empty string result here
        return ""


NOTIFY_COLORS = {
    "WARNING": "bright_red",
    "ERROR": "bright_red",
    "SUCCESS": "bright_green",
    "INFO": "blue",
}


def notify(type_, msg):
    """Prepends a message with a colored tag and outputs it to the console."""
    click.echo(f"{click.style(type_, fg=NOTIFY_COLORS[type_])}: {msg}")


class Abort(click.ClickException):
    """Wrapper around a CLI exception"""

    def show(self, file=None):
        """Override default `show` to print CLI errors in red text."""
        click.secho(f"Error: {self.format_message()}", err=True, fg="bright_red")


def deep_merge(dict1, dict2):
    """Return a new dictionary by merging two dictionaries recursively."""

    result = deepcopy(dict1)

    for key, value in dict2.items():
        if isinstance(value, collections.Mapping):
            result[key] = deep_merge(result.get(key, {}), value)
        else:
            result[key] = deepcopy(dict2[key])

    return result


def expand_environment_variables(contents: str) -> str:
    return os.path.expandvars(contents)


def load_config(path: Path, expand_envars=True, must_exist=False) -> Dict:
    if path.exists():
        contents = path.read_text()
        if expand_envars:
            contents = expand_environment_variables(contents)

        if path.suffix in (".json",):
            config = json.loads(contents)
        elif path.suffix in (".yml", ".yaml"):
            config = yaml.safe_load(contents)
        else:
            raise TypeError(f"Cannot parse '{path.suffix}' files!")

        return config or {}

    elif must_exist:
        raise IOError(f"{path} does not exist!")

    else:
        return {}


def compute_checksum(source: bytes, algorithm: str = "md5") -> str:
    if algorithm == "md5":
        hasher = md5
    else:
        raise Exception("Unknown algorithm")

    return hasher(source).hexdigest()


__all__ = [
    "cached_property",
    "deep_merge",
    "expand_environment_variables",
    "load_config",
    "notify",
    "singledispatchmethod",
]
