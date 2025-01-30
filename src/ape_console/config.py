from pydantic_settings import SettingsConfigDict

from ape.api.config import PluginConfig


class ConsoleConfig(PluginConfig):
    plugins: list[str] = []
    """Additional IPython plugins to include in your session."""

    model_config = SettingsConfigDict(extra="allow", env_prefix="APE_CONSOLE_")
