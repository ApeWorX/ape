from ape.api.config import PluginConfig


class CacheConfig(PluginConfig):
    size: int = 1024**3  # 1gb
