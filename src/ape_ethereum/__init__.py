from ape import plugins
from ape.api import create_network_type

from .ecosystem import NETWORKS, Ethereum


@plugins.register(plugins.EcosystemPlugin)
def ecosystems():
    yield Ethereum


@plugins.register(plugins.NetworkPlugin)
def networks():
    for network_name, network_params in NETWORKS.items():
        yield "ethereum", network_name, create_network_type(*network_params)

    # TODO: Move to ape-test 1st party plugin
    yield "ethereum", "development", create_network_type(chain_id=69, network_id=69)
