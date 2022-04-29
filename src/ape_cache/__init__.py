from ape import plugins
from ape.api import PluginConfig

from .query import CacheQueryProvider


class CacheConfig(PluginConfig):
    size: int = 1024**3  # 1gb


@plugins.register(plugins.Config)
def config_class():
    return CacheConfig


@plugins.register(plugins.QueryPlugin)
def query_engines():
    return CacheQueryProvider
