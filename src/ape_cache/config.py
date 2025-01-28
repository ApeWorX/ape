from pydantic_settings import SettingsConfigDict

from ape.api.config import PluginConfig


class CacheConfig(PluginConfig):
    size: int = 1024**3  # 1gb
    model_config = SettingsConfigDict(extra="allow", env_prefix="APE_CACHE_")
