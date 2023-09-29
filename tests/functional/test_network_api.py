import pytest

from ape.exceptions import NetworkError


def test_get_provider_when_not_found(ethereum):
    network = ethereum.get_network("goerli-fork")
    expected = "'test' is not a valid provider for network 'goerli-fork'"
    with pytest.raises(NetworkError, match=expected):
        network.get_provider("test")


def test_block_times(ethereum):
    assert ethereum.goerli.block_time == 15


def test_set_defaul_provider_not_exists(temp_config, ape_caplog, networks):
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
