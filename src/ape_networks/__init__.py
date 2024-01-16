from typing import Dict, List, Optional

from ape import plugins
from ape.api import PluginConfig


class CustomNetwork(PluginConfig):
    name: str
    chain_id: int
    ecosystem: Optional[str] = None
    default_provider: str = "geth"  # Default node.
    request_header: Dict = {}


class NetworksConfig(PluginConfig):
    custom: List[CustomNetwork] = []


@plugins.register(plugins.Config)
def config_class():
    return NetworksConfig
