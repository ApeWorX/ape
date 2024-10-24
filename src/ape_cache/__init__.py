from importlib import import_module

from ape import plugins
from ape.api.config import PluginConfig


class CacheConfig(PluginConfig):
    size: int = 1024**3  # 1gb


@plugins.register(plugins.Config)
def config_class():
    return CacheConfig


@plugins.register(plugins.QueryPlugin)
def query_engines():
    query = import_module("ape_cache.query")
    return query.CacheQueryProvider


def __getattr__(name):
    if name == "CacheQueryProvider":
        query = import_module("ape_cache.query")
        return query.CacheQueryProvider

    else:
        raise AttributeError(name)


__all__ = [
    "CacheQueryProvider",
]
