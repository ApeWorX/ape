import pytest

from ape import chain, networks


@pytest.hookimpl(trylast=True, hookwrapper=True)
def pytest_collection_finish(session):
    with networks.parse_network_choice("::test"):
        yield


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):
    snapshot_id = chain.snapshot()
    yield
    chain.restore(snapshot_id)


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
