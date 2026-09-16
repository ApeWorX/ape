from pydantic import Field
from pydantic_settings import SettingsConfigDict

from ape.api.config import PluginConfig


class ConsoleConfig(PluginConfig):
    plugins: list[str] = Field(default_factory=list)
    """Additional IPython plugins to include in your session."""

    model_config = SettingsConfigDict(extra="allow", env_prefix="APE_CONSOLE_")
