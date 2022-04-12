# Add module top-level imports here
from ape import plugins
from ape.api import PluginConfig

class CacheConfig(PluginConfig):
    size: int = 1024 ** 3  # 1gb


@plugins.register(plugins.Config)
def config_class():
    return CacheConfig
