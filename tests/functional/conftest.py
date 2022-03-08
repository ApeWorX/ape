import pytest
from eth.exceptions import HeaderNotFound

from ape import chain, networks
from ape.api import (
    AccountContainerAPI,
    EcosystemAPI,
    NetworkAPI,
    PluginConfig,
    ProviderAPI,
    ReceiptAPI,
    TransactionAPI,
    TransactionStatusEnum,
)
from ape.exceptions import ChainError, ContractLogicError

TEST_ADDRESS = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"


@pytest.fixture
def mock_account_container_api(mocker):
    return mocker.MagicMock(spec=AccountContainerAPI)


@pytest.fixture
def mock_provider_api(mocker, mock_network_api):
    mock = mocker.MagicMock(spec=ProviderAPI)
    mock.network = mock_network_api
    return mock


class _ContractLogicError(ContractLogicError):
    pass


@pytest.fixture
def mock_network_api(mocker):
    mock = mocker.MagicMock(spec=NetworkAPI)
    mock_ecosystem = mocker.MagicMock(spec=EcosystemAPI)
    mock_ecosystem.virtual_machine_error_class = _ContractLogicError
    mock.ecosystem = mock_ecosystem
    return mock


@pytest.fixture
def mock_failing_transaction_receipt(mocker):
    mock = mocker.MagicMock(spec=ReceiptAPI)
    mock.status = TransactionStatusEnum.FAILING
    mock.gas_used = 0
    return mock


@pytest.fixture
def mock_web3(mocker):
    return mocker.MagicMock()


@pytest.fixture
def mock_config_item(mocker):
    return mocker.MagicMock(spec=PluginConfig)


@pytest.fixture
def mock_transaction(mocker):
    return mocker.MagicMock(spec=TransactionAPI)


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
