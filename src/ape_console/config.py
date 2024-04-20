from ape.api import PluginConfig


class ConsoleConfig(PluginConfig):
    plugins: list[str] = []
    """Additional IPython plugins to include in your session."""
