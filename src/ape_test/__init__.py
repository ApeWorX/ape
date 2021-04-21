from ape import plugins
from ape.api import create_network_type

from .providers import LocalNetwork


@plugins.register(plugins.NetworkPlugin)
def networks():
    yield "ethereum", "development", create_network_type(chain_id=69, network_id=69)


@plugins.register(plugins.ProviderPlugin)
def providers():
    yield "ethereum", "development", LocalNetwork
