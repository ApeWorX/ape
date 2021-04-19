import collections
import json
import os
from copy import deepcopy
from pathlib import Path as Path
from typing import Dict

import click
import yaml

try:
    from functools import cached_property
except ImportError:
    from backports.cached_property import cached_property  # type: ignore

try:
    from functools import singledispatchmethod
except ImportError:
    from singledispatchmethod import singledispatchmethod  # type: ignore

NOTIFY_COLORS = {
    "WARNING": "bright_red",
    "ERROR": "bright_red",
    "SUCCESS": "bright_green",
    "INFO": "blue",
}


def notify(type_, msg):
    """Prepends a message with a colored tag and outputs it to the console."""
    click.echo(f"{click.style(type_, fg=NOTIFY_COLORS[type_])}: {msg}")


def deep_merge(dict1, dict2):
    """ Return a new dictionary by merging two dictionaries recursively. """

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

        return config

    elif must_exist:
        raise IOError(f"{path} does not exist!")

    else:
        return {}


__all__ = [
    "cached_property",
    "deep_merge",
    "expand_environment_variables",
    "load_config",
    "notify",
    "singledispatchmethod",
]
