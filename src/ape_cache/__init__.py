from importlib import import_module

from ape.plugins import Config, QueryPlugin, register


@register(Config)
def config_class():
    from ape_cache.config import CacheConfig

    return CacheConfig


@register(QueryPlugin)
def query_engines():
    query = import_module("ape_cache.query")
    return query.CacheQueryProvider


def __getattr__(name):
    if name == "CacheQueryProvider":
        module = import_module("ape_cache.query")
        return module.CacheQueryProvider

    elif name == "CacheConfig":
        module = import_module("ape_cache.config")
        return module.CacheConfig

    else:
        raise AttributeError(name)


__all__ = [
    "CacheConfig",
    "CacheQueryProvider",
]
