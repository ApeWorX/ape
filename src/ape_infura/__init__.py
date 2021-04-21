from ape import plugins

from .providers import Infura

NETWORKS = [
    "mainnet",
    "ropsten",
    "rinkeby",
    "kovan",
    "goerli",
]


@plugins.register(plugins.ProviderPlugin)
def providers():
    for network_name in NETWORKS:
        yield "ethereum", network_name, Infura
