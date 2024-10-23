from ape.api.config import PluginConfig


class ConsoleConfig(PluginConfig):
    plugins: list[str] = []
    """Additional IPython plugins to include in your session."""
