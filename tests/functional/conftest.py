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
        "bytecode": "608060405234801561001057600080fd5b50600080546001600160a01b03191633179055610714806100326000396000f3fe608060405234801561001057600080fd5b50600436106101005760003560e01c806351c0398011610097578063a2fbee5311610066578063a2fbee53146101ea578063a420b5a514610200578063e9f7fd1414610215578063f82bd81e1461022b57600080fd5b806351c03980146101855780637e9895fa1461019b57806381119130146101aa5780638da5cb5b146101bf57600080fd5b806329521aef116100d357806329521aef146101525780633fb5c1cb146101675780634825cf6f1461017c57806348d17a781461018557600080fd5b806302f487d614610105578063039b50441461012357806309b1b3f21461013457806323fd0e4014610149575b600080fd5b61010d610240565b60405161011a9190610517565b60405180910390f35b607b5b60405190815260200161011a565b61013c610281565b60405161011a919061052b565b61012660015481565b61015a6102b9565b60405161011a919061054b565b61017a61017536600461057c565b6102e3565b005b61012660025481565b60408051607b815261014160208201520161011a565b606060405161011a9190610595565b6101b2610381565b60405161011a91906105d9565b6000546101d2906001600160a01b031681565b6040516001600160a01b03909116815260200161011a565b6101f26103a0565b60405161011a92919061060a565b6102086103d1565b60405161011a9190610643565b61021d6103fa565b60405161011a92919061066c565b610233610446565b60405161011a9190610687565b604080516080810182526000818301818152606083018290528252602082015281518083019092529080610272610281565b81526020016001815250905090565b604080518082019091526000808252602082015260408051808201909152338152602081016102b16001436106b9565b409052919050565b6102c1610461565b5060408051606081018252600181526002602082015260039181019190915290565b6000546001600160a01b0316331461032f5760405162461bcd60e51b815260206004820152600b60248201526a08585d5d1a1bdc9a5e995960aa1b604482015260640160405180910390fd5b8060050361033c57600080fd5b6001805460028190559082905560405190815281907f2295d5ec33e3af0d43cc4b73aa3cd7d784150fe365cbdb4b4fd338220e4f13579060200160405180910390a250565b61038961047f565b506040805180820190915233808252602082015290565b60006103aa61049d565b60026040518060400160405280600281526020016103c6610281565b815250915091509091565b6103d961049d565b6040518060400160405280600281526020016103f3610281565b9052919050565b604080516080810182526000918101828152606082018390528152602081019190915260006040518060400160405280610432610281565b815260200160018152506001915091509091565b61044e6104ce565b5060408051602081019091526001815290565b60405180606001604052806003906020820280368337509192915050565b60405180604001604052806002906020820280368337509192915050565b6040518060400160405280600081526020016104c9604080518082019091526000808252602082015290565b905290565b60405180602001604052806001906020820280368337509192915050565b61050a82825180516001600160a01b03168252602090810151910152565b6020015160409190910152565b6060810161052582846104ec565b92915050565b81516001600160a01b031681526020808301519082015260408101610525565b60608101818360005b6003811015610573578151835260209283019290910190600101610554565b50505092915050565b60006020828403121561058e57600080fd5b5035919050565b6020808252825182820181905260009190848201906040850190845b818110156105cd578351835292840192918401916001016105b1565b50909695505050505050565b60408101818360005b60028110156105735781516001600160a01b03168352602092830192909101906001016105e2565b8281526080810161063c60208301848051825260209081015180516001600160a01b0316828401520151604090910152565b9392505050565b8151815260208083015180516001600160a01b0316828401520151604082015260608101610525565b6080810161067a82856104ec565b8260608301529392505050565b602081810190828460005b60018110156106af57815183529183019190830190600101610692565b5050505092915050565b6000828210156106d957634e487b7160e01b600052601160045260246000fd5b50039056fea26469706673582212205703266499b7f1ecf424e76fbee795c5fc9a73ec32a30507aeb3fb17b56e079664736f6c634300080d0033"
    },
    "runtimeBytecode": {
        "bytecode": "608060405234801561001057600080fd5b50600436106101005760003560e01c806351c0398011610097578063a2fbee5311610066578063a2fbee53146101ea578063a420b5a514610200578063e9f7fd1414610215578063f82bd81e1461022b57600080fd5b806351c03980146101855780637e9895fa1461019b57806381119130146101aa5780638da5cb5b146101bf57600080fd5b806329521aef116100d357806329521aef146101525780633fb5c1cb146101675780634825cf6f1461017c57806348d17a781461018557600080fd5b806302f487d614610105578063039b50441461012357806309b1b3f21461013457806323fd0e4014610149575b600080fd5b61010d610240565b60405161011a9190610517565b60405180910390f35b607b5b60405190815260200161011a565b61013c610281565b60405161011a919061052b565b61012660015481565b61015a6102b9565b60405161011a919061054b565b61017a61017536600461057c565b6102e3565b005b61012660025481565b60408051607b815261014160208201520161011a565b606060405161011a9190610595565b6101b2610381565b60405161011a91906105d9565b6000546101d2906001600160a01b031681565b6040516001600160a01b03909116815260200161011a565b6101f26103a0565b60405161011a92919061060a565b6102086103d1565b60405161011a9190610643565b61021d6103fa565b60405161011a92919061066c565b610233610446565b60405161011a9190610687565b604080516080810182526000818301818152606083018290528252602082015281518083019092529080610272610281565b81526020016001815250905090565b604080518082019091526000808252602082015260408051808201909152338152602081016102b16001436106b9565b409052919050565b6102c1610461565b5060408051606081018252600181526002602082015260039181019190915290565b6000546001600160a01b0316331461032f5760405162461bcd60e51b815260206004820152600b60248201526a08585d5d1a1bdc9a5e995960aa1b604482015260640160405180910390fd5b8060050361033c57600080fd5b6001805460028190559082905560405190815281907f2295d5ec33e3af0d43cc4b73aa3cd7d784150fe365cbdb4b4fd338220e4f13579060200160405180910390a250565b61038961047f565b506040805180820190915233808252602082015290565b60006103aa61049d565b60026040518060400160405280600281526020016103c6610281565b815250915091509091565b6103d961049d565b6040518060400160405280600281526020016103f3610281565b9052919050565b604080516080810182526000918101828152606082018390528152602081019190915260006040518060400160405280610432610281565b815260200160018152506001915091509091565b61044e6104ce565b5060408051602081019091526001815290565b60405180606001604052806003906020820280368337509192915050565b60405180604001604052806002906020820280368337509192915050565b6040518060400160405280600081526020016104c9604080518082019091526000808252602082015290565b905290565b60405180602001604052806001906020820280368337509192915050565b61050a82825180516001600160a01b03168252602090810151910152565b6020015160409190910152565b6060810161052582846104ec565b92915050565b81516001600160a01b031681526020808301519082015260408101610525565b60608101818360005b6003811015610573578151835260209283019290910190600101610554565b50505092915050565b60006020828403121561058e57600080fd5b5035919050565b6020808252825182820181905260009190848201906040850190845b818110156105cd578351835292840192918401916001016105b1565b50909695505050505050565b60408101818360005b60028110156105735781516001600160a01b03168352602092830192909101906001016105e2565b8281526080810161063c60208301848051825260209081015180516001600160a01b0316828401520151604090910152565b9392505050565b8151815260208083015180516001600160a01b0316828401520151604082015260608101610525565b6080810161067a82856104ec565b8260608301529392505050565b602081810190828460005b60018110156106af57815183529183019190830190600101610692565b5050505092915050565b6000828210156106d957634e487b7160e01b600052601160045260246000fd5b50039056fea26469706673582212205703266499b7f1ecf424e76fbee795c5fc9a73ec32a30507aeb3fb17b56e079664736f6c634300080d0033"
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
            "name": "getNestedStruct1",
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
                        },
                        {"name": "foo", "type": "uint256", "internalType": "uint256"},
                    ],
                    "internalType": "struct TestContractSol.NestedStruct1",
                }
            ],
        },
        {
            "type": "function",
            "name": "getNestedStruct2",
            "stateMutability": "view",
            "inputs": [],
            "outputs": [
                {
                    "name": "",
                    "type": "tuple",
                    "components": [
                        {"name": "foo", "type": "uint256", "internalType": "uint256"},
                        {
                            "name": "t",
                            "type": "tuple",
                            "components": [
                                {"name": "a", "type": "address", "internalType": "address"},
                                {"name": "b", "type": "bytes32", "internalType": "bytes32"},
                            ],
                            "internalType": "struct TestContractSol.MyStruct",
                        },
                    ],
                    "internalType": "struct TestContractSol.NestedStruct2",
                }
            ],
        },
        {
            "type": "function",
            "name": "getNestedStructWithTuple1",
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
                        },
                        {"name": "foo", "type": "uint256", "internalType": "uint256"},
                    ],
                    "internalType": "struct TestContractSol.NestedStruct1",
                },
                {"name": "", "type": "uint256", "internalType": "uint256"},
            ],
        },
        {
            "type": "function",
            "name": "getNestedStructWithTuple2",
            "stateMutability": "view",
            "inputs": [],
            "outputs": [
                {"name": "", "type": "uint256", "internalType": "uint256"},
                {
                    "name": "",
                    "type": "tuple",
                    "components": [
                        {"name": "foo", "type": "uint256", "internalType": "uint256"},
                        {
                            "name": "t",
                            "type": "tuple",
                            "components": [
                                {"name": "a", "type": "address", "internalType": "address"},
                                {"name": "b", "type": "bytes32", "internalType": "bytes32"},
                            ],
                            "internalType": "struct TestContractSol.MyStruct",
                        },
                    ],
                    "internalType": "struct TestContractSol.NestedStruct2",
                },
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
        "bytecode": "0x336000556103b361001c6300000000396103b36000016300000000f3600436101561000d576103a8565b60003560e01c346103ae57633fb5c1cb81186100d057600054331461008957600b6040527f21617574686f72697a65640000000000000000000000000000000000000000006060526040506040518060600181600003601f1636823750506308c379a06000526020602052601f19601f6040510116604401601cfd5b6005600435146103ae576001546002556004356001556004357f2295d5ec33e3af0d43cc4b73aa3cd7d784150fe365cbdb4b4fd338220e4f135760025460405260206040a2005b6309b1b3f281186100ed5733604052600143034060605260406040f35b6302f487d6811861010f57336040526001430340606052600160805260606040f35b63a420b5a5811861013157600260405233606052600143034060805260606040f35b63e9f7fd148118610158573360405260014303406060526001608052600160a05260806040f35b63a2fbee53811861017f576002604052600260605233608052600143034060a05260806040f35b637e9895fa81186101da5760208060405280604001600060008252600060006000600181116103ae5780156101c757905b6000602082026020870101526001018181186101b0575b5050810160200190509050810190506040f35b63f82bd81e811861024d57602080604052806040016000600160a052600160c052600060a05180845260208102600082600181116103ae57801561023757905b6020810260c001516020820260208901015260010181811861021a575b5050820160200191505090509050810190506040f35b6329521aef81186102ce57602080604052806040016000600360e052600161010052600261012052600361014052600060e05180845260208102600082600381116103ae5780156102b857905b6020810261010001516020820260208901015260010181811861029a575b5050820160200191505090509050810190506040f35b6381119130811861034557602080604052806040016000600260c0523360e0523361010052600060c05180845260208102600082600281116103ae57801561032f57905b6020810260e0015160208202602089010152600101818118610312575b5050820160200191505090509050810190506040f35b63650543a3811861036157607b60405261014160605260406040f35b638da5cb5b81186103785760005460405260206040f35b6323fd0e40811861038f5760015460405260206040f35b634825cf6f81186103a65760025460405260206040f35b505b60006000fd5b600080fd"
    },
    "runtimeBytecode": {
        "bytecode": "0x600436101561000d576103a8565b60003560e01c346103ae57633fb5c1cb81186100d057600054331461008957600b6040527f21617574686f72697a65640000000000000000000000000000000000000000006060526040506040518060600181600003601f1636823750506308c379a06000526020602052601f19601f6040510116604401601cfd5b6005600435146103ae576001546002556004356001556004357f2295d5ec33e3af0d43cc4b73aa3cd7d784150fe365cbdb4b4fd338220e4f135760025460405260206040a2005b6309b1b3f281186100ed5733604052600143034060605260406040f35b6302f487d6811861010f57336040526001430340606052600160805260606040f35b63a420b5a5811861013157600260405233606052600143034060805260606040f35b63e9f7fd148118610158573360405260014303406060526001608052600160a05260806040f35b63a2fbee53811861017f576002604052600260605233608052600143034060a05260806040f35b637e9895fa81186101da5760208060405280604001600060008252600060006000600181116103ae5780156101c757905b6000602082026020870101526001018181186101b0575b5050810160200190509050810190506040f35b63f82bd81e811861024d57602080604052806040016000600160a052600160c052600060a05180845260208102600082600181116103ae57801561023757905b6020810260c001516020820260208901015260010181811861021a575b5050820160200191505090509050810190506040f35b6329521aef81186102ce57602080604052806040016000600360e052600161010052600261012052600361014052600060e05180845260208102600082600381116103ae5780156102b857905b6020810261010001516020820260208901015260010181811861029a575b5050820160200191505090509050810190506040f35b6381119130811861034557602080604052806040016000600260c0523360e0523361010052600060c05180845260208102600082600281116103ae57801561032f57905b6020810260e0015160208202602089010152600101818118610312575b5050820160200191505090509050810190506040f35b63650543a3811861036157607b60405261014160605260406040f35b638da5cb5b81186103785760005460405260206040f35b6323fd0e40811861038f5760015460405260206040f35b634825cf6f81186103a65760025460405260206040f35b505b60006000fd5b600080fd"
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
            "name": "getNestedStruct1",
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
                        },
                        {"name": "foo", "type": "uint256"},
                    ],
                }
            ],
        },
        {
            "type": "function",
            "name": "getNestedStruct2",
            "stateMutability": "view",
            "inputs": [],
            "outputs": [
                {
                    "name": "",
                    "type": "tuple",
                    "components": [
                        {"name": "foo", "type": "uint256"},
                        {
                            "name": "t",
                            "type": "tuple",
                            "components": [
                                {"name": "a", "type": "address"},
                                {"name": "b", "type": "bytes32"},
                            ],
                        },
                    ],
                }
            ],
        },
        {
            "type": "function",
            "name": "getNestedStructWithTuple1",
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
                        },
                        {"name": "foo", "type": "uint256"},
                    ],
                },
                {"name": "", "type": "uint256"},
            ],
        },
        {
            "type": "function",
            "name": "getNestedStructWithTuple2",
            "stateMutability": "view",
            "inputs": [],
            "outputs": [
                {"name": "", "type": "uint256"},
                {
                    "name": "",
                    "type": "tuple",
                    "components": [
                        {"name": "foo", "type": "uint256"},
                        {
                            "name": "t",
                            "type": "tuple",
                            "components": [
                                {"name": "a", "type": "address"},
                                {"name": "b", "type": "bytes32"},
                            ],
                        },
                    ],
                },
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
    return solidity_contract_container if request.param == "solidity" else vyper_contract_container


@pytest.fixture(params=("solidity", "vyper"))
def contract_instance(request, solidity_contract_instance, vyper_contract_instance):
    return solidity_contract_instance if request.param == "solidity" else vyper_contract_instance
