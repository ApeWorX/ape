from typing import Dict, List, Optional

from ape import plugins
from ape.api import PluginConfig


class CustomNetwork(PluginConfig):
    """
    A custom network config.
    """

    """Name of the network e.g. mainnet."""
    name: str

    """Chain ID (required)."""
    chain_id: int

    """The name of the ecosystem."""
    ecosystem: str

    """The base ecosystem plugin to use, when applicable. Defaults to the default ecosystem."""
    base_ecosystem_plugin: Optional[str] = None

    """The default provider plugin to use. Default is the default node provider."""
    default_provider: str = "geth"

    """The HTTP request header."""
    request_header: Dict = {}


class NetworksConfig(PluginConfig):
    custom: List[CustomNetwork] = []


@plugins.register(plugins.Config)
def config_class():
    return NetworksConfig
