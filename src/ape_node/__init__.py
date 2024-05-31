from ape import plugins
from ape.api.networks import LOCAL_NETWORK_NAME

from .provider import EthereumNetworkConfig, EthereumNodeConfig, GethDev, Node
from .query import OtterscanQueryEngine


@plugins.register(plugins.Config)
def config_class():
    return EthereumNodeConfig


@plugins.register(plugins.ProviderPlugin)
def providers():
    networks_dict = EthereumNetworkConfig().model_dump()
    networks_dict.pop(LOCAL_NETWORK_NAME)
    for network_name in networks_dict:
        yield "ethereum", network_name, Node

    yield "ethereum", LOCAL_NETWORK_NAME, GethDev


@plugins.register(plugins.QueryPlugin)
def query_engines():
    yield OtterscanQueryEngine


__all__ = [
    "EthereumNetworkConfig",
    "EthereumNodeConfig",
    "GethDev",
    "Node",
    "OtterscanQueryEngine",
]
