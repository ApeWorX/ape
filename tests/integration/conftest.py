import pytest
from eth.exceptions import HeaderNotFound

from ape import chain, networks
from ape.exceptions import ChainError


@pytest.hookimpl(trylast=True, hookwrapper=True)
def pytest_collection_finish(session):
    with networks.parse_network_choice("::test"):
        # Sets the active provider
        yield


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):
    module_name = item.module.__name__
    prefix = "tests.integration"

    # Only do snapshotting for non-functional and non-CLI tests.
    if module_name.startswith(prefix) and not module_name.startswith(f"{prefix}.cli"):
        snapshot_id = chain.snapshot()
        yield

        try:
            chain.restore(snapshot_id)
        except (HeaderNotFound, ChainError):
            pass
    else:
        yield


@pytest.fixture
def networks_connected_to_tester():
    with networks.parse_network_choice("::test"):
        yield networks


@pytest.fixture
def ethereum(networks_connected_to_tester):
    return networks_connected_to_tester.ethereum


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
