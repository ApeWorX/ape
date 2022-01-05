import pytest

from ape import networks


@pytest.fixture
def networks_connected_to_tester():
    with networks.parse_network_choice("::test"):
        yield networks


@pytest.fixture
def eth_tester_provider(networks_connected_to_tester):
    yield networks_connected_to_tester.active_provider


@pytest.fixture
def ethereum(networks_connected_to_tester):
    return networks_connected_to_tester.ethereum
