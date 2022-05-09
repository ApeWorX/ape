import json
from pathlib import Path
from typing import Dict

import pytest
from eth.exceptions import HeaderNotFound
from ethpm_types import ContractType

import ape
from ape.api import (
    AccountContainerAPI,
    EcosystemAPI,
    NetworkAPI,
    PluginConfig,
    ProviderAPI,
    ReceiptAPI,
    TransactionAPI,
)
from ape.contracts import ContractContainer, ContractInstance
from ape.exceptions import ChainError, ContractLogicError, ProviderNotConnectedError
from ape_ethereum.transactions import TransactionStatusEnum


def _get_raw_contract(compiler: str) -> Dict:
    here = Path(__file__).parent
    contracts_dir = here / "data" / "contracts"
    return json.loads((contracts_dir / f"{compiler}_contract.json").read_text())


RAW_SOLIDITY_CONTRACT_TYPE = _get_raw_contract("solidity")
RAW_VYPER_CONTRACT_TYPE = _get_raw_contract("vyper")
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
    with ape.networks.parse_network_choice("::test"):
        # Sets the active provider
        yield


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):
    module_name = item.module.__name__
    prefix = "tests.functional"

    if module_name.startswith(prefix):
        snapshot_id = ape.chain.snapshot()
        yield

        try:
            ape.chain.restore(snapshot_id)
        except (HeaderNotFound, ChainError, ProviderNotConnectedError):
            pass
    else:
        yield


@pytest.fixture(scope="session")
def networks_connected_to_tester():
    with ape.networks.parse_network_choice("::test"):
        yield ape.networks


@pytest.fixture(scope="session")
def ethereum(networks_connected_to_tester):
    return networks_connected_to_tester.ethereum


@pytest.fixture(scope="session")
def eth_tester_provider(networks_connected_to_tester):
    yield networks_connected_to_tester.active_provider


@pytest.fixture
def test_accounts(accounts):
    return accounts.test_accounts


@pytest.fixture
def sender(test_accounts):
    return test_accounts[0]


@pytest.fixture
def receiver(test_accounts):
    return test_accounts[1]


@pytest.fixture
def owner(test_accounts):
    return test_accounts[2]


@pytest.fixture
def solidity_contract_type() -> ContractType:
    return ContractType.parse_obj(RAW_SOLIDITY_CONTRACT_TYPE)


@pytest.fixture
def solidity_contract_container(solidity_contract_type) -> ContractContainer:
    return ContractContainer(contract_type=solidity_contract_type)


@pytest.fixture
def solidity_contract_instance(
    owner, solidity_contract_container, networks_connected_to_tester
) -> ContractInstance:
    return owner.deploy(solidity_contract_container)


@pytest.fixture
def vyper_contract_type() -> ContractType:
    return ContractType.parse_obj(RAW_VYPER_CONTRACT_TYPE)


@pytest.fixture
def vyper_contract_container(vyper_contract_type) -> ContractContainer:
    return ContractContainer(contract_type=vyper_contract_type)


@pytest.fixture
def vyper_contract_instance(
    owner, vyper_contract_container, networks_connected_to_tester
) -> ContractInstance:
    return owner.deploy(vyper_contract_container)


@pytest.fixture(params=("solidity", "vyper"))
def contract_container(
    request, solidity_contract_container, vyper_contract_container, networks_connected_to_tester
):
    return solidity_contract_container if request.param == "solidity" else vyper_contract_container


@pytest.fixture(params=("solidity", "vyper"))
def contract_instance(request, solidity_contract_instance, vyper_contract_instance):
    return solidity_contract_instance if request.param == "solidity" else vyper_contract_instance
