from ape import plugins


@plugins.register(plugins.Config)
def config_class():
    from ape_ethereum.ecosystem import EthereumConfig

    return EthereumConfig


@plugins.register(plugins.ConversionPlugin)
def converters():
    from ape_ethereum._converters import WeiConversions

    yield int, WeiConversions


@plugins.register(plugins.EcosystemPlugin)
def ecosystems():
    from ape_ethereum.ecosystem import Ethereum

    yield Ethereum


@plugins.register(plugins.NetworkPlugin)
def networks():
    from ape.api.networks import ForkedNetworkAPI, NetworkAPI, create_network_type
    from ape_ethereum.ecosystem import NETWORKS

    for network_name, network_params in NETWORKS.items():
        yield "ethereum", network_name, create_network_type(*network_params)
        yield "ethereum", f"{network_name}-fork", ForkedNetworkAPI

    # NOTE: This works for local providers, as they get chain_id from themselves
    yield "ethereum", "local", NetworkAPI


@plugins.register(plugins.QueryPlugin)
def query_engines():
    from .query import EthereumQueryProvider

    yield EthereumQueryProvider


def __getattr__(name):
    if name in (
        "BaseEthereumConfig",
        "Block",
        "Ethereum",
        "EthereumConfig",
        "ForkedNetworkConfig",
        "NetworkConfig",
    ):
        import ape_ethereum.ecosystem as ecosystem_module

        return getattr(ecosystem_module, name)

    elif name in (
        "EthereumNodeProvider",
        "Web3Provider",
        "assert_web3_provider_uri_env_var_not_set",
    ):
        import ape_ethereum.provider as provider_module

        return getattr(provider_module, name)

    elif name in (
        "AccessListTransaction",
        "BaseTransaction",
        "DynamicFeeTransaction",
        "Receipt",
        "SharedBlobReceipt",
        "SharedBlobTransaction",
        "StaticFeeTransaction",
        "TransactionStatusEnum",
        "TransactionType",
    ):
        import ape_ethereum.transactions as tx_module

        return getattr(tx_module, name)

    elif name in ("CallTrace", "Trace", "TransactionTrace"):
        import ape_ethereum.trace as trace_module

        return getattr(trace_module, name)

    else:
        raise AttributeError(name)


__all__ = [
    "AccessListTransaction",
    "assert_web3_provider_uri_env_var_not_set",
    "BaseEthereumConfig",
    "BaseTransaction",
    "Block",
    "CallTrace",
    "DynamicFeeTransaction",
    "Ethereum",
    "EthereumConfig",
    "EthereumNodeProvider",
    "ForkedNetworkConfig",
    "NetworkConfig",
    "Receipt",
    "SharedBlobReceipt",
    "SharedBlobTransaction",
    "StaticFeeTransaction",
    "Trace",
    "TransactionStatusEnum",
    "TransactionTrace",
    "TransactionType",
    "SharedBlobTransaction",
    "Web3Provider",
]
