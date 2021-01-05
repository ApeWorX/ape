from typing import Dict, List

import collections
import json
import os
import yaml

from copy import deepcopy
from pathlib import Path as Path


LOADER = {
    ".json": json.loads,
    ".yml": yaml.safe_load,
    ".yaml": yaml.safe_load,
}


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
        return LOADER[path.suffix](contents)
    elif must_exist:
        raise IOError(f"{path} does not exist!")
    else:
        return {}
