from typing import Dict, List, Optional

from ape import plugins
from ape.api import PluginConfig


class CustomNetwork(PluginConfig):
    """
    A custom network config.
    """

    """Name of the network e.g. mainnet"""
    name: str

    """Chain ID (required)"""
    chain_id: int

    """The name of the ecosystem"""
    ecosystem: Optional[str] = None

    """The base ecosystem plugin to use, when applicable"""
    base_ecosystem_plugin: Optional[str] = None

    """The default provider plugin to use"""
    default_provider: str = "geth"  # Default node.

    """The HTTP request header"""
    request_header: Dict = {}


class NetworksConfig(PluginConfig):
    custom: List[CustomNetwork] = []


@plugins.register(plugins.Config)
def config_class():
    return NetworksConfig
