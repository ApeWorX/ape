from typing import List

from ape.api import PluginConfig


class ConsoleConfig(PluginConfig):
    plugins: List[str] = []
    """Additional IPython plugins to include in your session."""
