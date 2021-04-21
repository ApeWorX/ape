from ape import plugins

from .explorer import Etherscan

NETWORKS = [
    "mainnet",
    "ropsten",
    "rinkeby",
    "kovan",
    "goerli",
]


@plugins.register(plugins.ExplorerPlugin)
def explorers():
    for network_name in NETWORKS:
        yield "ethereum", network_name, Etherscan
