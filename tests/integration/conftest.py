import pytest

from ape import networks


@pytest.fixture
def in_test_network():
    with networks.parse_network_choice("::test"):
        yield
