from typing import Optional

from ape import plugins
from ape.api.config import PluginConfig


class CustomNetwork(PluginConfig):
    """
    A custom network config.
    """

    name: str
    """Name of the network e.g. mainnet."""

    chain_id: int
    """Chain ID (required)."""

    ecosystem: str
    """The name of the ecosystem."""

    base_ecosystem_plugin: Optional[str] = None
    """The base ecosystem plugin to use, when applicable. Defaults to the default ecosystem."""

    default_provider: str = "node"
    """The default provider plugin to use. Default is the default node provider."""

    request_header: dict = {}
    """The HTTP request header."""

    @property
    def is_fork(self) -> bool:
        """
        ``True`` when the name of the network ends in ``"-fork"``.
        """
        return self.name.endswith("-fork")


class NetworksConfig(PluginConfig):
    custom: list[CustomNetwork] = []


@plugins.register(plugins.Config)
def config_class():
    return NetworksConfig
