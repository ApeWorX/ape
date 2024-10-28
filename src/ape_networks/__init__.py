from typing import Any

from ape.plugins import Config, register


@register(Config)
def config_class():
    from ape_networks.config import NetworksConfig

    return NetworksConfig


def __getattr__(name: str) -> Any:
    if name == "NetworksConfig":
        from ape_networks.config import NetworksConfig

        return NetworksConfig

    else:
        raise AttributeError(name)


__all__ = ["NetworksConfig"]
