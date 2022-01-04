import pytest
from eth.exceptions import HeaderNotFound

from ape import chain, networks


@pytest.hookimpl(trylast=True, hookwrapper=True)
def pytest_collection_finish(session):
    with networks.parse_network_choice("::test"):
        yield


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):
    snapshot_id = chain.snapshot()
    yield

    try:
        chain.restore(snapshot_id)
    except HeaderNotFound:
        pass  # Not sure why this happens sometimes...


@pytest.fixture
def eth_tester_provider(networks):
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
