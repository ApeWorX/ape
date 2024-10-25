from ape import plugins
from ape.api.networks import ForkedNetworkAPI, NetworkAPI, create_network_type

from ._converters import WeiConversions
from .ecosystem import (
    NETWORKS,
    BaseEthereumConfig,
    Block,
    Ethereum,
    EthereumConfig,
    ForkedNetworkConfig,
    NetworkConfig,
)
from .provider import EthereumNodeProvider, Web3Provider, assert_web3_provider_uri_env_var_not_set
from .query import EthereumQueryProvider
from .trace import CallTrace, Trace, TransactionTrace
from .transactions import (
    AccessListTransaction,
    BaseTransaction,
    DynamicFeeTransaction,
    Receipt,
    SharedBlobReceipt,
    SharedBlobTransaction,
    StaticFeeTransaction,
    TransactionStatusEnum,
    TransactionType,
)


@plugins.register(plugins.Config)
def config_class():
    return EthereumConfig


@plugins.register(plugins.ConversionPlugin)
def converters():
    yield int, WeiConversions


@plugins.register(plugins.EcosystemPlugin)
def ecosystems():
    yield Ethereum


@plugins.register(plugins.NetworkPlugin)
def networks():
    for network_name, network_params in NETWORKS.items():
        yield "ethereum", network_name, create_network_type(*network_params)
        yield "ethereum", f"{network_name}-fork", ForkedNetworkAPI

    # NOTE: This works for local providers, as they get chain_id from themselves
    yield "ethereum", "local", NetworkAPI


@plugins.register(plugins.QueryPlugin)
def query_engines():
    yield EthereumQueryProvider


__all__ = [
    "Ethereum",
    "EthereumConfig",
    "NetworkConfig",
    "ForkedNetworkConfig",
    "BaseEthereumConfig",
    "Block",
    "assert_web3_provider_uri_env_var_not_set",
    "Web3Provider",
    "EthereumNodeProvider",
    "Trace",
    "TransactionTrace",
    "CallTrace",
    "TransactionStatusEnum",
    "TransactionType",
    "BaseTransaction",
    "StaticFeeTransaction",
    "AccessListTransaction",
    "DynamicFeeTransaction",
    "SharedBlobTransaction",
    "Receipt",
    "SharedBlobReceipt",
]
