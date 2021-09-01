from ape import plugins
from ape.api import NetworkAPI, create_network_type

from .converters import WeiConversions
from .ecosystem import NETWORKS, Ethereum


@plugins.register(plugins.ConversionPlugin)
def converters():
    yield int, WeiConversions


@plugins.register(plugins.EcosystemPlugin)
def ecosystems():
    yield Ethereum


@plugins.register(plugins.NetworkPlugin)
def networks():
    for network_name, network_params in NETWORKS.items():
        yield "ethereum", network_name, create_network_type(*network_params)

    # NOTE: This works for `geth --dev` as it gets chain_id from itself
    yield "ethereum", "development", NetworkAPI
