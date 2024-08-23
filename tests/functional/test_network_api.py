import copy
from pathlib import Path

import pytest

from ape.api.networks import ForkedNetworkAPI, NetworkAPI, create_network_type
from ape.api.providers import ProviderAPI
from ape.exceptions import NetworkError, ProviderNotFoundError
from ape_ethereum import EthereumConfig
from ape_ethereum.transactions import TransactionType


def test_get_provider_when_not_found(ethereum):
    name = "sepolia-fork"
    network = ethereum.get_network(name)
    expected = f"No provider named 'test' in network '{name}' in ecosystem 'ethereum'.*"
    with pytest.raises(ProviderNotFoundError, match=expected):
        network.get_provider("test")


@pytest.mark.parametrize("scheme", ("http", "https", "ws", "wss"))
def test_get_provider_http(ethereum, scheme):
    uri = f"{scheme}://example.com"
    network = ethereum.get_network("sepolia")
    actual = network.get_provider(uri)
    assert actual.uri == uri
    assert actual.network.name == "sepolia"


def test_get_provider_ipc(ethereum):
    path = "path/to/geth.ipc"
    network = ethereum.get_network("sepolia")
    actual = network.get_provider(path)
    assert actual.ipc_path == Path(path)
    assert actual.network.name == "sepolia"


def test_get_provider_custom_network(project, custom_networks_config_dict, ethereum):
    with project.temp_config(**custom_networks_config_dict):
        network = ethereum.apenet
        actual = network.get_provider("node")
        assert isinstance(actual, ProviderAPI)
        assert actual.name == "node"


def test_block_times(ethereum):
    assert ethereum.sepolia.block_time == 15


def test_set_default_provider_not_exists(ape_caplog, ethereum):
    bad_provider = "NOT_EXISTS"
    expected = f"Provider '{bad_provider}' not found in network 'ethereum:sepolia'."
    with pytest.raises(NetworkError, match=expected):
        ethereum.sepolia.set_default_provider(bad_provider)


def test_gas_limits(ethereum, project, custom_networks_config_dict):
    """
    Test the default gas limit configurations for local and live networks.
    """
    with project.temp_config(**custom_networks_config_dict):
        assert ethereum.sepolia.gas_limit == "auto"
        assert ethereum.local.gas_limit == "max"


def test_base_fee_multiplier(ethereum):
    assert ethereum.mainnet.base_fee_multiplier == 1.4
    assert ethereum.local.base_fee_multiplier == 1.0


def test_forked_networks(ethereum):
    mainnet_fork = ethereum.mainnet_fork
    ethereum.mainnet._default_provider = "node"  # In case changed elsewhere in env.
    assert mainnet_fork.upstream_network.name == "mainnet"
    assert mainnet_fork.upstream_chain_id == 1
    # Just make sure it doesn't fail when trying to access.
    assert mainnet_fork.upstream_provider
    # Ensure has default configurations.
    cfg = mainnet_fork.ecosystem_config.mainnet_fork
    assert cfg.default_transaction_type == TransactionType.DYNAMIC
    assert cfg.block_time == 0
    assert cfg.default_provider is None
    assert cfg.base_fee_multiplier == 1.0
    assert cfg.transaction_acceptance_timeout == 20
    assert cfg.max_receipt_retries == 20


def test_forked_network_with_config(project, ethereum):
    data = {
        "ethereum": {"mainnet_fork": {"default_transaction_type": TransactionType.STATIC.value}}
    }
    with project.temp_config(**data):
        cfg = ethereum.mainnet_fork.config
        assert cfg.default_transaction_type == TransactionType.STATIC
        assert cfg.block_time == 0
        assert cfg.default_provider is None
        assert cfg.base_fee_multiplier == 1.0
        assert cfg.transaction_acceptance_timeout == 20
        assert cfg.max_receipt_retries == 20
        assert cfg.gas_limit == "max"


def test_data_folder_custom_network(custom_network, ethereum, custom_network_name_0):
    actual = custom_network.data_folder
    expected = ethereum.data_folder / custom_network_name_0
    assert actual == expected


def test_config_custom_networks_default(ethereum, project, custom_networks_config_dict):
    """
    Shows you don't get AttributeError when custom network config is not
    present.
    """
    with project.temp_config(**custom_networks_config_dict):
        network = ethereum.apenet
        cfg = network.config
        assert cfg.default_transaction_type == TransactionType.DYNAMIC


def test_config_custom_networks(
    ethereum, custom_networks_config_dict, project, custom_network_name_0
):
    data = copy.deepcopy(custom_networks_config_dict)
    data["ethereum"] = {
        custom_network_name_0: {"default_transaction_type": TransactionType.STATIC.value}
    }
    with project.temp_config(**data):
        network = ethereum.apenet
        ethereum_config = network.ecosystem_config
        cfg_by_attr = ethereum_config.apenet
        assert cfg_by_attr.default_transaction_type == TransactionType.STATIC

        assert "apenet" in ethereum_config
        cfg_by_get = ethereum_config.get("apenet")
        assert cfg_by_get is not None
        assert cfg_by_get.default_transaction_type == TransactionType.STATIC


def test_config_networks_from_custom_ecosystem(
    networks, custom_networks_config_dict, project, custom_network_name_0
):
    data = copy.deepcopy(custom_networks_config_dict)
    data["networks"]["custom"][0]["ecosystem"] = "custom-ecosystem"
    data["networks"]["custom"][1]["ecosystem"] = "custom-ecosystem"
    data["custom-ecosystem"] = {
        custom_network_name_0: {"default_transaction_type": TransactionType.STATIC.value}
    }
    with project.temp_config(**data):
        custom_ecosystem = networks.get_ecosystem("custom-ecosystem")
        network = custom_ecosystem.get_network("apenet")
        ecosystem_config = network.ecosystem_config
        network_by_attr = ecosystem_config.apenet
        network_by_get = ecosystem_config.get("apenet")

    assert custom_ecosystem.name == "custom-ecosystem"

    # Show .get_network() works (raises when not found).
    assert network.name == "apenet"

    # Show custom ecosystems have a config.
    assert isinstance(ecosystem_config, EthereumConfig)

    # Show contains works.
    assert "apenet" in ecosystem_config

    # Show dot-access works (raise AttrError when not found).
    assert network_by_attr.default_transaction_type == TransactionType.STATIC

    # Show .get() works (returns None when not found).
    assert network_by_get is not None
    assert network_by_get.default_transaction_type == TransactionType.STATIC


def test_use_provider_using_provider_instance(eth_tester_provider):
    network = eth_tester_provider.network
    with network.use_provider(eth_tester_provider) as provider:
        assert id(provider) == id(eth_tester_provider)


def test_use_provider_previously_used_and_not_connected(eth_tester_provider):
    network = eth_tester_provider.network
    eth_tester_provider.disconnect()
    with network.use_provider("test") as provider:
        assert provider.is_connected


def test_create_network_type():
    chain_id = 123321123321123321
    actual = create_network_type(chain_id, chain_id)
    assert issubclass(actual, NetworkAPI)


def test_create_network_type_fork():
    chain_id = 123321123321123322
    actual = create_network_type(chain_id, chain_id, is_fork=True)
    assert issubclass(actual, NetworkAPI)
    assert issubclass(actual, ForkedNetworkAPI)


def test_providers(ethereum):
    network = ethereum.local
    providers = network.providers
    assert "test" in providers
    assert "node" in providers


def test_providers_custom_network(project, custom_networks_config_dict, ethereum):
    with project.temp_config(**custom_networks_config_dict):
        network = ethereum.apenet
        actual = network.providers
        assert "node" in actual


def test_providers_custom_non_fork_network_does_not_use_fork_provider(
    mocker, project, custom_networks_config_dict, ethereum
):
    # NOTE: Have to a mock a Fork provider since none ship with Ape core.
    with project.temp_config(**custom_networks_config_dict):
        network = ethereum.apenet
        network.__dict__.pop("providers", None)  # de-cache

        # Setup mock fork provider.
        orig = network._get_plugin_providers
        network._get_plugin_providers = mocker.MagicMock()
        name = "foobar"

        class MyForkProvider:
            __module__ = "foobar.test"

        network._get_plugin_providers.return_value = iter(
            [(name, ("ethereum", "local", MyForkProvider))]
        )
        try:
            actual = network.providers
            assert name not in actual
        finally:
            network._get_plugin_providers = orig
            network.__dict__.pop("providers", None)  # de-cache
