from ape import plugins
from ape.api import NetworkAPI, create_network_type
from ape.api.networks import LOCAL_NETWORK_NAME

from ._converters import WeiConversions
from .ecosystem import NETWORKS, Ethereum, EthereumConfig


@plugins.register(plugins.Config)
def config_class():
    return EthereumConfig


@plugins.register(plugins.ConversionPlugin)
def converters():
    yield int, WeiConversions


@plugins.register(plugins.EcosystemPlugin)
def ecosystems():
    yield Ethereum


@plugins.register(plugins.NetworkPlugin)
def networks():
    for network_name, network_params in NETWORKS.items():
        network_api = create_network_type(*network_params)
        yield "ethereum", network_name, network_api

    # NOTE: This works for development providers, as they get chain_id from themselves
    yield "ethereum", LOCAL_NETWORK_NAME, NetworkAPI
    yield "ethereum", "mainnet-fork", NetworkAPI
