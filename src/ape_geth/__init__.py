from ape import plugins
from ape.api.networks import LOCAL_NETWORK_NAME

from .provider import Geth as GethProvider
from .provider import GethConfig, GethDev, GethNetworkConfig
from .query import OTSQueryEngine


@plugins.register(plugins.Config)
def config_class():
    return GethConfig


@plugins.register(plugins.ProviderPlugin)
def providers():
    networks_dict = GethNetworkConfig().model_dump(mode="json")
    networks_dict.pop(LOCAL_NETWORK_NAME)
    for network_name in networks_dict:
        yield "ethereum", network_name, GethProvider

    yield "ethereum", LOCAL_NETWORK_NAME, GethDev


@plugins.register(plugins.QueryPlugin)
def query_engines():
    yield OTSQueryEngine
