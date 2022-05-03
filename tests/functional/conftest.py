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

TEST_ADDRESS = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
RAW_SOLIDITY_CONTRACT_TYPE = {
    "contractName": "TestContractSol",
    "sourceId": "TestContractSol.sol",
    "deploymentBytecode": {
        "bytecode": "608060405234801561001057600080fd5b50600080546001600160a01b031916331790556104ed806100326000396000f3fe608060405234801561001057600080fd5b50600436106100cf5760003560e01c80634825cf6f1161008c5780637e9895fa116100665780637e9895fa1461016657806381119130146101755780638da5cb5b1461018a578063f82bd81e146101b557600080fd5b80634825cf6f1461014757806348d17a781461015057806351c039801461015057600080fd5b8063039b5044146100d457806309b1b3f2146100ea57806323fd0e40146100ff57806329521aef146101085780633e9245a51461011d5780633fb5c1cb14610132575b600080fd5b607b5b6040519081526020015b60405180910390f35b6100f26101ca565b6040516100e1919061035d565b6100d760015481565b610110610202565b6040516100e1919061037f565b61012561022c565b6040516100e191906103b0565b6101456101403660046103d2565b610260565b005b6100d760025481565b60408051607b81526101416020820152016100e1565b60606040516100e191906103eb565b61017d6102c9565b6040516100e1919061042f565b60005461019d906001600160a01b031681565b6040516001600160a01b0390911681526020016100e1565b6101bd6102e8565b6040516100e19190610460565b604080518082019091526000808252602082015260408051808201909152338152602081016101fa600143610492565b409052919050565b61020a610303565b5060408051606081018252600181526002602082015260039181019190915290565b604080516060810182526000602082018181529282015290815260405180602001604052806102596101ca565b9052919050565b6000546001600160a01b0316331461027757600080fd5b8060050361028457600080fd5b6001805460028190559082905560405190815281907f2295d5ec33e3af0d43cc4b73aa3cd7d784150fe365cbdb4b4fd338220e4f13579060200160405180910390a250565b6102d1610321565b506040805180820190915233808252602082015290565b6102f061033f565b5060408051602081019091526001815290565b60405180606001604052806003906020820280368337509192915050565b60405180604001604052806002906020820280368337509192915050565b60405180602001604052806001906020820280368337509192915050565b81516001600160a01b0316815260208083015190820152604081015b92915050565b60608101818360005b60038110156103a7578151835260209283019290910190600101610388565b50505092915050565b815180516001600160a01b031682526020908101519082015260408101610379565b6000602082840312156103e457600080fd5b5035919050565b6020808252825182820181905260009190848201906040850190845b8181101561042357835183529284019291840191600101610407565b50909695505050505050565b60408101818360005b60028110156103a75781516001600160a01b0316835260209283019290910190600101610438565b602081810190828460005b60018110156104885781518352918301919083019060010161046b565b5050505092915050565b6000828210156104b257634e487b7160e01b600052601160045260246000fd5b50039056fea2646970667358221220f43314750c8c9cb0e13abf508d276c057832cca11e1aaf57d0e22d8f1aee8c0464736f6c634300080d0033"  # noqa: E501
    },
    "runtimeBytecode": {
        "bytecode": "608060405234801561001057600080fd5b50600436106100cf5760003560e01c80634825cf6f1161008c5780637e9895fa116100665780637e9895fa1461016657806381119130146101755780638da5cb5b1461018a578063f82bd81e146101b557600080fd5b80634825cf6f1461014757806348d17a781461015057806351c039801461015057600080fd5b8063039b5044146100d457806309b1b3f2146100ea57806323fd0e40146100ff57806329521aef146101085780633e9245a51461011d5780633fb5c1cb14610132575b600080fd5b607b5b6040519081526020015b60405180910390f35b6100f26101ca565b6040516100e1919061035d565b6100d760015481565b610110610202565b6040516100e1919061037f565b61012561022c565b6040516100e191906103b0565b6101456101403660046103d2565b610260565b005b6100d760025481565b60408051607b81526101416020820152016100e1565b60606040516100e191906103eb565b61017d6102c9565b6040516100e1919061042f565b60005461019d906001600160a01b031681565b6040516001600160a01b0390911681526020016100e1565b6101bd6102e8565b6040516100e19190610460565b604080518082019091526000808252602082015260408051808201909152338152602081016101fa600143610492565b409052919050565b61020a610303565b5060408051606081018252600181526002602082015260039181019190915290565b604080516060810182526000602082018181529282015290815260405180602001604052806102596101ca565b9052919050565b6000546001600160a01b0316331461027757600080fd5b8060050361028457600080fd5b6001805460028190559082905560405190815281907f2295d5ec33e3af0d43cc4b73aa3cd7d784150fe365cbdb4b4fd338220e4f13579060200160405180910390a250565b6102d1610321565b506040805180820190915233808252602082015290565b6102f061033f565b5060408051602081019091526001815290565b60405180606001604052806003906020820280368337509192915050565b60405180604001604052806002906020820280368337509192915050565b60405180602001604052806001906020820280368337509192915050565b81516001600160a01b0316815260208083015190820152604081015b92915050565b60608101818360005b60038110156103a7578151835260209283019290910190600101610388565b50505092915050565b815180516001600160a01b031682526020908101519082015260408101610379565b6000602082840312156103e457600080fd5b5035919050565b6020808252825182820181905260009190848201906040850190845b8181101561042357835183529284019291840191600101610407565b50909695505050505050565b60408101818360005b60028110156103a75781516001600160a01b0316835260209283019290910190600101610438565b602081810190828460005b60018110156104885781518352918301919083019060010161046b565b5050505092915050565b6000828210156104b257634e487b7160e01b600052601160045260246000fd5b50039056fea2646970667358221220f43314750c8c9cb0e13abf508d276c057832cca11e1aaf57d0e22d8f1aee8c0464736f6c634300080d0033"  # noqa: E501
    },
    "abi": [
        {"type": "constructor", "stateMutability": "nonpayable", "inputs": []},
        {
            "type": "event",
            "name": "NumberChange",
            "inputs": [
                {"name": "prevNum", "type": "uint256", "internalType": "uint256", "indexed": False},
                {"name": "newNum", "type": "uint256", "internalType": "uint256", "indexed": True},
            ],
            "anonymous": False,
        },
        {
            "type": "function",
            "name": "getAddressList",
            "stateMutability": "view",
            "inputs": [],
            "outputs": [{"name": "", "type": "address[2]", "internalType": "address[2]"}],
        },
        {
            "type": "function",
            "name": "getEmptyList",
            "stateMutability": "pure",
            "inputs": [],
            "outputs": [{"name": "", "type": "uint256[]", "internalType": "uint256[]"}],
        },
        {
            "type": "function",
            "name": "getFilledList",
            "stateMutability": "pure",
            "inputs": [],
            "outputs": [{"name": "", "type": "uint256[3]", "internalType": "uint256[3]"}],
        },
        {
            "type": "function",
            "name": "getNamedSingleItem",
            "stateMutability": "pure",
            "inputs": [],
            "outputs": [{"name": "foo", "type": "uint256", "internalType": "uint256"}],
        },
        {
            "type": "function",
            "name": "getNestedStruct",
            "stateMutability": "view",
            "inputs": [],
            "outputs": [
                {
                    "name": "",
                    "type": "tuple",
                    "components": [
                        {
                            "name": "t",
                            "type": "tuple",
                            "components": [
                                {"name": "a", "type": "address", "internalType": "address"},
                                {"name": "b", "type": "bytes32", "internalType": "bytes32"},
                            ],
                            "internalType": "struct TestContractSol.MyStruct",
                        }
                    ],
                    "internalType": "struct TestContractSol.NestedStruct",
                }
            ],
        },
        {
            "type": "function",
            "name": "getPartiallyNamedTuple",
            "stateMutability": "pure",
            "inputs": [],
            "outputs": [
                {"name": "foo", "type": "uint256", "internalType": "uint256"},
                {"name": "", "type": "uint256", "internalType": "uint256"},
            ],
        },
        {
            "type": "function",
            "name": "getSingleItemList",
            "stateMutability": "pure",
            "inputs": [],
            "outputs": [{"name": "", "type": "uint256[1]", "internalType": "uint256[1]"}],
        },
        {
            "type": "function",
            "name": "getStruct",
            "stateMutability": "view",
            "inputs": [],
            "outputs": [
                {
                    "name": "",
                    "type": "tuple",
                    "components": [
                        {"name": "a", "type": "address", "internalType": "address"},
                        {"name": "b", "type": "bytes32", "internalType": "bytes32"},
                    ],
                    "internalType": "struct TestContractSol.MyStruct",
                }
            ],
        },
        {
            "type": "function",
            "name": "getTupleAllNamed",
            "stateMutability": "pure",
            "inputs": [],
            "outputs": [
                {"name": "foo", "type": "uint256", "internalType": "uint256"},
                {"name": "bar", "type": "uint256", "internalType": "uint256"},
            ],
        },
        {
            "type": "function",
            "name": "myNumber",
            "stateMutability": "view",
            "inputs": [],
            "outputs": [{"name": "", "type": "uint256", "internalType": "uint256"}],
        },
        {
            "type": "function",
            "name": "owner",
            "stateMutability": "view",
            "inputs": [],
            "outputs": [{"name": "", "type": "address", "internalType": "address"}],
        },
        {
            "type": "function",
            "name": "prevNumber",
            "stateMutability": "view",
            "inputs": [],
            "outputs": [{"name": "", "type": "uint256", "internalType": "uint256"}],
        },
        {
            "type": "function",
            "name": "setNumber",
            "stateMutability": "nonpayable",
            "inputs": [{"name": "num", "type": "uint256", "internalType": "uint256"}],
            "outputs": [],
        },
    ],
    "userdoc": {"kind": "user", "methods": {}, "version": 1},
    "devdoc": {"kind": "dev", "methods": {}, "version": 1},
}
RAW_VYPER_CONTRACT_TYPE = {
    "contractName": "TestContractVy",
    "sourceId": "TestContractVy.vy",
    "deploymentBytecode": {
        "bytecode": "0x3360005561033e61001c63000000003961033e6000016300000000f3600436101561000d57610333565b60003560e01c3461033957633fb5c1cb81186100d057600054331461008957600b6040527f21617574686f72697a65640000000000000000000000000000000000000000006060526040506040518060600181600003601f1636823750506308c379a06000526020602052601f19601f6040510116604401601cfd5b600560043514610339576001546002556004356001556004357f2295d5ec33e3af0d43cc4b73aa3cd7d784150fe365cbdb4b4fd338220e4f135760025460405260206040a2005b6309b1b3f281186100ed5733604052600143034060605260406040f35b633e9245a5811861010a5733604052600143034060605260406040f35b637e9895fa811861016557602080604052806040016000600082526000600060006001811161033957801561015257905b60006020820260208701015260010181811861013b575b5050810160200190509050810190506040f35b63f82bd81e81186101d857602080604052806040016000600160a052600160c052600060a05180845260208102600082600181116103395780156101c257905b6020810260c00151602082026020890101526001018181186101a5575b5050820160200191505090509050810190506040f35b6329521aef811861025957602080604052806040016000600360e052600161010052600261012052600361014052600060e051808452602081026000826003811161033957801561024357905b60208102610100015160208202602089010152600101818118610225575b5050820160200191505090509050810190506040f35b638111913081186102d057602080604052806040016000600260c0523360e0523361010052600060c05180845260208102600082600281116103395780156102ba57905b6020810260e001516020820260208901015260010181811861029d575b5050820160200191505090509050810190506040f35b63650543a381186102ec57607b60405261014160605260406040f35b638da5cb5b81186103035760005460405260206040f35b6323fd0e40811861031a5760015460405260206040f35b634825cf6f81186103315760025460405260206040f35b505b60006000fd5b600080fd"  # noqa: E501
    },
    "runtimeBytecode": {
        "bytecode": "0x600436101561000d57610333565b60003560e01c3461033957633fb5c1cb81186100d057600054331461008957600b6040527f21617574686f72697a65640000000000000000000000000000000000000000006060526040506040518060600181600003601f1636823750506308c379a06000526020602052601f19601f6040510116604401601cfd5b600560043514610339576001546002556004356001556004357f2295d5ec33e3af0d43cc4b73aa3cd7d784150fe365cbdb4b4fd338220e4f135760025460405260206040a2005b6309b1b3f281186100ed5733604052600143034060605260406040f35b633e9245a5811861010a5733604052600143034060605260406040f35b637e9895fa811861016557602080604052806040016000600082526000600060006001811161033957801561015257905b60006020820260208701015260010181811861013b575b5050810160200190509050810190506040f35b63f82bd81e81186101d857602080604052806040016000600160a052600160c052600060a05180845260208102600082600181116103395780156101c257905b6020810260c00151602082026020890101526001018181186101a5575b5050820160200191505090509050810190506040f35b6329521aef811861025957602080604052806040016000600360e052600161010052600261012052600361014052600060e051808452602081026000826003811161033957801561024357905b60208102610100015160208202602089010152600101818118610225575b5050820160200191505090509050810190506040f35b638111913081186102d057602080604052806040016000600260c0523360e0523361010052600060c05180845260208102600082600281116103395780156102ba57905b6020810260e001516020820260208901015260010181811861029d575b5050820160200191505090509050810190506040f35b63650543a381186102ec57607b60405261014160605260406040f35b638da5cb5b81186103035760005460405260206040f35b6323fd0e40811861031a5760015460405260206040f35b634825cf6f81186103315760025460405260206040f35b505b60006000fd5b600080fd"  # noqa: E501
    },
    "abi": [
        {
            "type": "event",
            "name": "NumberChange",
            "inputs": [
                {"name": "prevNum", "type": "uint256", "indexed": False},
                {"name": "newNum", "type": "uint256", "indexed": True},
            ],
            "anonymous": False,
        },
        {"type": "constructor", "stateMutability": "nonpayable", "inputs": []},
        {
            "type": "function",
            "name": "setNumber",
            "stateMutability": "nonpayable",
            "inputs": [{"name": "num", "type": "uint256"}],
            "outputs": [],
        },
        {
            "type": "function",
            "name": "getStruct",
            "stateMutability": "view",
            "inputs": [],
            "outputs": [
                {
                    "name": "",
                    "type": "tuple",
                    "components": [
                        {"name": "a", "type": "address"},
                        {"name": "b", "type": "bytes32"},
                    ],
                }
            ],
        },
        {
            "type": "function",
            "name": "getNestedStruct",
            "stateMutability": "view",
            "inputs": [],
            "outputs": [
                {
                    "name": "",
                    "type": "tuple",
                    "components": [
                        {
                            "name": "t",
                            "type": "tuple",
                            "components": [
                                {"name": "a", "type": "address"},
                                {"name": "b", "type": "bytes32"},
                            ],
                        }
                    ],
                }
            ],
        },
        {
            "type": "function",
            "name": "getEmptyList",
            "stateMutability": "pure",
            "inputs": [],
            "outputs": [{"name": "", "type": "uint256[]"}],
        },
        {
            "type": "function",
            "name": "getSingleItemList",
            "stateMutability": "pure",
            "inputs": [],
            "outputs": [{"name": "", "type": "uint256[]"}],
        },
        {
            "type": "function",
            "name": "getFilledList",
            "stateMutability": "pure",
            "inputs": [],
            "outputs": [{"name": "", "type": "uint256[]"}],
        },
        {
            "type": "function",
            "name": "getAddressList",
            "stateMutability": "view",
            "inputs": [],
            "outputs": [{"name": "", "type": "address[]"}],
        },
        {
            "type": "function",
            "name": "getMultipleValues",
            "stateMutability": "pure",
            "inputs": [],
            "outputs": [{"name": "", "type": "uint256"}, {"name": "", "type": "uint256"}],
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
            "name": "myNumber",
            "stateMutability": "view",
            "inputs": [],
            "outputs": [{"name": "", "type": "uint256"}],
        },
        {
            "type": "function",
            "name": "prevNumber",
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
    if request.param == "solidity":
        yield solidity_contract_container
    elif request.param == "vyper":
        yield vyper_contract_container


@pytest.fixture(params=("solidity", "vyper"))
def contract_instance(request, solidity_contract_instance, vyper_contract_instance):
    if request.param == "solidity":
        yield solidity_contract_instance
    elif request.param == "vyper":
        yield vyper_contract_instance
