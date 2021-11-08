from ape import plugins

from .providers import EthereumNetworkConfig, GethProvider, NetworkConfig


@plugins.register(plugins.Config)
def config_class():
    return NetworkConfig


@plugins.register(plugins.ProviderPlugin)
def providers():
    for network_name in EthereumNetworkConfig().serialize():
        yield "ethereum", network_name, GethProvider
