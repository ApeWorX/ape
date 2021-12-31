import pytest

from ape_test.providers import LocalNetwork


@pytest.fixture
def eth_tester_provider():
    return LocalNetwork()
