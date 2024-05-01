from typing import Dict, List, Optional

from ape import plugins
from ape.api import PluginConfig


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

    default_provider: str = "geth"
    """The default provider plugin to use. Default is the default node provider."""

    request_header: Dict = {}
    """The HTTP request header."""


class NetworksConfig(PluginConfig):
    custom: List[CustomNetwork] = []


@plugins.register(plugins.Config)
def config_class():
    return NetworksConfig
