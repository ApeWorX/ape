from ape import plugins
from ape.api.networks import LOCAL_NETWORK_NAME

from .provider import Geth as GethProvider
from .provider import GethDev, GethNetworkConfig, NetworkConfig


@plugins.register(plugins.Config)
def config_class():
    return NetworkConfig


@plugins.register(plugins.ProviderPlugin)
def providers():
    networks_dict = GethNetworkConfig().dict()
    networks_dict.pop(LOCAL_NETWORK_NAME)
    for network_name in networks_dict:
        yield "ethereum", network_name, GethProvider

    yield "ethereum", LOCAL_NETWORK_NAME, GethDev
