from typing import Any

from ape.plugins import Config as RConfig
from ape.plugins import register


@register(RConfig)
def config_class():
    from ape_compile.config import Config

    return Config


def __getattr__(name: str) -> Any:
    if name == "Config":
        from ape_compile.config import Config

        return Config

    else:
        raise AttributeError(name)


__all__ = [
    "Config",
]
