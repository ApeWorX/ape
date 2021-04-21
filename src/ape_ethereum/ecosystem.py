from ape.api import EcosystemAPI

NETWORKS = {
    # chain_id, network_id
    "mainnet": (1, 1),
    "ropsten": (3, 3),
    "kovan": (42, 42),
    "rinkeby": (4, 4),
    "goerli": (420, 420),
}


class Ethereum(EcosystemAPI):
    pass


# TODO: Define VM-specific stuff here
