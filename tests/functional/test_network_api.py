from pathlib import Path

import pytest

from ape.exceptions import NetworkError, ProviderNotFoundError


def test_get_provider_when_not_found(ethereum):
    name = "goerli-fork"
    network = ethereum.get_network(name)
    expected = f"No provider named 'test' in network '{name}' in ecosystem 'ethereum'.*"
    with pytest.raises(ProviderNotFoundError, match=expected):
        network.get_provider("test")


@pytest.mark.parametrize("scheme", ("http", "https", "ws", "wss"))
def test_get_provider_http(ethereum, scheme):
    uri = f"{scheme}://example.com"
    network = ethereum.get_network("goerli")
    actual = network.get_provider(uri)
    assert actual.uri == uri


def test_get_provider_ipc(ethereum):
    path = "path/to/geth.ipc"
    network = ethereum.get_network("goerli")
    actual = network.get_provider(path)
    assert actual.ipc_path == Path(path)


def test_block_times(ethereum):
    assert ethereum.goerli.block_time == 15


def test_set_default_provider_not_exists(temp_config, ape_caplog, networks):
    bad_provider = "NOT_EXISTS"
    expected = f"Provider '{bad_provider}' not found in network 'ethereum:goerli'."
    with pytest.raises(NetworkError, match=expected):
        networks.ethereum.goerli.set_default_provider(bad_provider)


def test_gas_limits(networks, config, project_with_source_files_contract):
    """
    Test the default gas limit configurations for local and live networks.
    """
    _ = project_with_source_files_contract  # Ensure use of project with default config
    assert networks.ethereum.goerli.gas_limit == "auto"
    assert networks.ethereum.local.gas_limit == "max"


def test_base_fee_multiplier(networks):
    assert networks.ethereum.mainnet.base_fee_multiplier == 1.4
    assert networks.ethereum.local.base_fee_multiplier == 1.0


def test_forked_networks(ethereum):
    mainnet_fork = ethereum.mainnet_fork
    assert mainnet_fork.upstream_network.name == "mainnet"
    assert mainnet_fork.upstream_chain_id == 1
    # Just make sure it doesn't fail when trying to access.
    assert mainnet_fork.upstream_provider
