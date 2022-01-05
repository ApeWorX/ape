import pytest

from ape import networks


@pytest.fixture
def eth_tester_provider():
    with networks.parse_network_choice("::test"):
        yield networks.active_provider


@pytest.fixture
def test_accounts(accounts):
    return accounts.test_accounts


@pytest.fixture
def sender(test_accounts):
    return test_accounts[0]


@pytest.fixture
def receiver(test_accounts):
    return test_accounts[1]
