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
    TransactionStatusEnum,
)
from ape.contracts import ContractContainer, ContractInstance
from ape.exceptions import ChainError, ContractLogicError

TEST_ADDRESS = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
RAW_CONTRACT_TYPE = {
    "contractName": "TestContract",
    "sourceId": "TestContract.vy",
    "deploymentBytecode": {
        "bytecode": "0x3360005561012656600436101561000d57610113565b600035601c52600051346101195763d6d1ee148114156100c9576000543314610075576308c379a061014052602061016052600b610180527f21617574686f72697a65640000000000000000000000000000000000000000006101a05261018050606461015cfd5b60056004351815610119576001546002556004356001556004357f2295d5ec33e3af0d43cc4b73aa3cd7d784150fe365cbdb4b4fd338220e4f135761014080808060025481525050602090509050610140a2005b638da5cb5b8114156100e15760005460005260206000f35b63be23d7b98114156100f95760015460005260206000f35b632b3979478114156101115760025460005260206000f35b505b60006000fd5b600080fd5b61000861012603610008600039610008610126036000f3"  # noqa: E501
    },
    "runtimeBytecode": {
        "bytecode": "0x600436101561000d57610113565b600035601c52600051346101195763d6d1ee148114156100c9576000543314610075576308c379a061014052602061016052600b610180527f21617574686f72697a65640000000000000000000000000000000000000000006101a05261018050606461015cfd5b60056004351815610119576001546002556004356001556004357f2295d5ec33e3af0d43cc4b73aa3cd7d784150fe365cbdb4b4fd338220e4f135761014080808060025481525050602090509050610140a2005b638da5cb5b8114156100e15760005460005260206000f35b63be23d7b98114156100f95760015460005260206000f35b632b3979478114156101115760025460005260206000f35b505b60006000fd5b600080fd"  # noqa: E501
    },
    "abi": [
        {
            "type": "event",
            "name": "NumberChange",
            "inputs": [
                {"name": "prev_num", "type": "uint256", "indexed": False},
                {"name": "new_num", "type": "uint256", "indexed": True},
            ],
            "anonymous": False,
        },
        {"type": "constructor", "stateMutability": "nonpayable", "inputs": []},
        {
            "type": "function",
            "name": "set_number",
            "stateMutability": "nonpayable",
            "inputs": [{"name": "num", "type": "uint256"}],
            "outputs": [],
        },
        {
            "type": "function",
            "name": "owner",
            "stateMutability": "view",
            "inputs": [],
            "outputs": [{"name": "", "type": "address"}],
        },
        {
            "type": "function",
            "name": "my_number",
            "stateMutability": "view",
            "inputs": [],
            "outputs": [{"name": "", "type": "uint256"}],
        },
        {
            "type": "function",
            "name": "prev_number",
            "stateMutability": "view",
            "inputs": [],
            "outputs": [{"name": "", "type": "uint256"}],
        },
    ],
    "userdoc": {},
    "devdoc": {},
}


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
        except (HeaderNotFound, ChainError):
            pass
    else:
        yield


@pytest.fixture
def networks_connected_to_tester():
    with ape.networks.parse_network_choice("::test"):
        yield ape.networks


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


@pytest.fixture
def owner(test_accounts):
    return test_accounts[2]


@pytest.fixture
def contract_type() -> ContractType:
    return ContractType.parse_obj(RAW_CONTRACT_TYPE)


@pytest.fixture
def contract_container(contract_type) -> ContractContainer:
    return ContractContainer(contract_type=contract_type)


@pytest.fixture
def contract_instance(owner, contract_container) -> ContractInstance:
    return owner.deploy(contract_container)
