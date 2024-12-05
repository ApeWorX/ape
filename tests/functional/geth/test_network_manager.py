import pytest

from ape.utils.misc import LOCAL_NETWORK_NAME
from tests.conftest import geth_process_test


@pytest.fixture
def mock_geth_sepolia(ethereum, geth_provider, geth_contract):
    """
    Temporarily tricks Ape into thinking the local network
    is Sepolia so we can test features that require a live
    network.
    """
    # Ensuring contract exists before hack.
    # This allow the network to be past genesis which is more realistic.
    _ = geth_contract
    geth_provider.network.name = "sepolia"
    yield geth_provider.network
    geth_provider.network.name = LOCAL_NETWORK_NAME


@geth_process_test
def test_fork_upstream_provider(networks, mock_geth_sepolia, geth_provider, mock_fork_provider):
    uri = "http://example.com/node"
    orig = geth_provider.provider_settings.get("uri")
    geth_provider.provider_settings["uri"] = uri
    try:
        with networks.fork():
            call = mock_fork_provider.partial_call

        settings = call[1]["provider_settings"]["fork"]["ethereum"]["sepolia"]
        actual = settings["upstream_provider"]
        assert actual == uri
    finally:
        # Restore.
        if orig:
            geth_provider.provider_settings["uri"] = orig
        else:
            del geth_provider.provider_settings["uri"]


# NOTE: Test is flakey because random URLs may be offline when test runs; avoid CI failure.
@pytest.mark.flaky(reruns=5)
@geth_process_test
@pytest.mark.parametrize(
    "connection_str", ("moonbeam:moonriver", "https://moonriver.api.onfinality.io/public")
)
def test_parse_network_choice_evmchains(networks, connection_str):
    """
    Show we can (without having a plugin installed) connect to a network
    that evm-chains knows about.
    """
    with networks.parse_network_choice(connection_str) as moon_provider:
        assert moon_provider.network.name == "moonriver"
        assert moon_provider.network.ecosystem.name == "moonbeam"
