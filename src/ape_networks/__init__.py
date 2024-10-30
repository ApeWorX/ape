from importlib import import_module

from ape.plugins import Config, register


@register(Config)
def config_class():
    from ape_networks.config import NetworksConfig

    return NetworksConfig


def __getattr__(name: str):
    if name in ("NetworksConfig", "CustomNetwork"):
        return getattr(import_module("ape_networks.config"), name)

    else:
        raise AttributeError(name)


__all__ = ["NetworksConfig"]
