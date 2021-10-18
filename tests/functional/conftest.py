import pytest

from ape.api import (
    AccountContainerAPI,
    EcosystemAPI,
    NetworkAPI,
    ProviderAPI,
    ReceiptAPI,
    TransactionAPI,
    TransactionStatusEnum,
)
from ape.api.config import ConfigItem
from ape.exceptions import VirtualMachineError

TEST_ADDRESS = "0x0A78AAAAA2122100000b9046f0A085AB2E111113"


@pytest.fixture
def mock_account_container_api(mocker):
    return mocker.MagicMock(spec=AccountContainerAPI)


@pytest.fixture
def mock_provider_api(mocker, mock_network_api):
    mock = mocker.MagicMock(spec=ProviderAPI)
    mock.network = mock_network_api
    return mock


class _MockVirtualMachineError(VirtualMachineError):
    pass


@pytest.fixture
def mock_network_api(mocker):
    mock = mocker.MagicMock(spec=NetworkAPI)
    mock_ecosystem = mocker.MagicMock(spec=EcosystemAPI)
    mock_ecosystem.virtual_machine_error_class = _MockVirtualMachineError
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
    return mocker.MagicMock(spec=ConfigItem)


@pytest.fixture
def mock_transaction(mocker):
    return mocker.MagicMock(spec=TransactionAPI)
