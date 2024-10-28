from importlib import import_module
from typing import Any

from ape.plugins import Config, register


@register(Config)
def config_class():
    from ape_networks.config import NetworksConfig

    return NetworksConfig


def __getattr__(name: str) -> Any:
    if name in ("NetworksConfig", "CustomNetwork"):
        return getattr(import_module("ape_networks.config"), name)

    else:
        raise AttributeError(name)


__all__ = ["NetworksConfig"]
