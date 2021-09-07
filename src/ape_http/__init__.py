from ape import plugins

from .providers import EcosystemConfig, EthereumNetworkConfig, EthereumProvider


@plugins.register(plugins.Config)
def config_class():
    return EcosystemConfig


@plugins.register(plugins.ProviderPlugin)
def providers():
    for network_name in EthereumNetworkConfig().dict():
        yield "ethereum", network_name, EthereumProvider
