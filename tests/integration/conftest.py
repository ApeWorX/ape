import pytest

from ape import networks


@pytest.fixture
def eth_tester_provider():
    with networks.parse_network_choice("::test"):
        yield networks.active_provider
