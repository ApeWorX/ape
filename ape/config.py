# NOTE: Modules in Python are singletons, this module implements
#       all of the configuration items for the ape tool
# https://docs.python.org/3/faq/programming.html#how-do-i-share-global-variables-across-modules
from typing import Dict
import sys as _sys

from pathlib import Path as _Path

from .constants import (
    INSTALL_FOLDER,
    PROJECT_FOLDER,
    DATA_FOLDER,
)
from ._utils import (
    deep_merge as _deep_merge,
    load_config as _load_config,
)

from ape import __version__


# For all HTTP requests we make
_python_version = (
    f"{_sys.version_info.major}.{_sys.version_info.minor}"
    f".{_sys.version_info.micro} {_sys.version_info.releaselevel}"
)
REQUEST_HEADERS = {"User-Agent": f"Ape/{__version__} (Python/{_python_version})"}

# Our example config file, with all the defaults set
DEFAULT_CONFIG = _load_config(INSTALL_FOLDER.joinpath("data/default-config.yaml"), must_exist=True)

# The config from the user's environment
_user_config = _load_config(PROJECT_FOLDER.joinpath("ape-config.yaml"))

# Configuration items (these can be modified from their initial state)
def get_merged_config(name: str) -> Dict:
    return _deep_merge(
        DEFAULT_CONFIG[name],
        _user_config.get(name, {}),
    )


# Do this so we have typing info for these objects
project_structure = get_merged_config("project_structure")
compiler = get_merged_config("compiler")
console = get_merged_config("console")
hypothesis = get_merged_config("hypothesis")
autofetch_sources = get_merged_config("autofetch_sources")
dependencies = get_merged_config("dependencies")
dev_deployment_artifacts = get_merged_config("dev_deployment_artifacts")
_user_network_settings = get_merged_config("networks")

# Allow using custom (unsupported) config items
custom = {k: v for k, v in _user_config.items() if k not in DEFAULT_CONFIG.keys()}

# Set up network configuration (these will change over time)
active_network = _user_network_settings.get("default", "development")

networks = _load_config(DATA_FOLDER.joinpath("network-config.yaml"))

# Merge project config file settings with global network settings
for name, params in networks["local"].items():
    networks["local"][name] = _deep_merge(params, _user_network_settings["local"])

for name, params in networks["public"].items():
    networks["public"][name] = _deep_merge(params, _user_network_settings["public"])


def _get_network_type(id: str) -> str:
    if id not in (*networks["local"].keys(), *networks["public"].keys()):
        raise ValueError(f"'{id}' is not a valid network name")

    if id in networks["local"].keys():
        return "local"
    else:
        return "public"


def get_active_network_params() -> Dict:
    if active_network is None:
        raise ConnectionError("No active network")

    typ = _get_network_type(active_network)
    if "fork" in active_network:
        # Handle "fork mode" differently
        fork = active_network.replace("-fork", "")
        params = _deep_merge(
            networks[_get_network_type(fork)][fork],
            networks[typ][active_network],
        )
        # This is the key difference
        params["cmd_settings"]["fork"] = networks[typ][fork]["host"]
        return params
    else:
        return networks[typ][active_network]


def set_active_network(id: str):
    _get_network_type(id)  # Raises if not valid
    active_network = id
