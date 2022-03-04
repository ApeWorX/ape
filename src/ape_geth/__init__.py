from ape import plugins

from .providers import GethNetworkConfig, GethProvider, NetworkConfig


@plugins.register(plugins.Config)
def config_class():
    return NetworkConfig


@plugins.register(plugins.ProviderPlugin)
def providers():
    for network_name in GethNetworkConfig().dict():
        yield "ethereum", network_name, GethProvider
