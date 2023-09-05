from pathlib import Path

from Contracts import ContractInstance

from ape import Contract


def test_load_solidity_contract_from_abi(
    solidity_contract_instance, solidity_contract_instance_abi
):
    abi = solidity_contract_instance_abi
    address = solidity_contract_instance.address

    contract = Contract(address, abi=abi)

    assert isinstance(contract, ContractInstance)
    assert contract.address == address
    assert contract.myNumber() == 0


def test_load_vyper_contract_from_abi(vyper_contract_instance, vyper_contract_instance_abi):
    abi = vyper_contract_instance_abi

    address = vyper_contract_instance.address

    contract = Contract(address, abi=abi)

    assert isinstance(contract, ContractInstance)
    assert contract.address == address
    assert contract.myNumber() == 0
    assert contract.balance == 0


def test_load_contract_from_abi_type_ABI(solidity_contract_instance):
    abi_list = [
        {
            "inputs": [{"internalType": "uint256", "name": "num", "type": "uint256"}],
            "stateMutability": "nonpayable",
            "type": "constructor",
        },
        {
            "anonymous": False,
            "inputs": [
                {
                    "indexed": True,
                    "internalType": "address",
                    "name": "newAddress",
                    "type": "address",
                }
            ],
            "name": "AddressChange",
            "type": "event",
        },
        {
            "anonymous": False,
            "inputs": [
                {"indexed": True, "internalType": "uint256", "name": "bar", "type": "uint256"}
            ],
            "name": "BarHappened",
            "type": "event",
        },
        {
            "anonymous": False,
            "inputs": [
                {"indexed": True, "internalType": "uint256", "name": "foo", "type": "uint256"}
            ],
            "name": "FooHappened",
            "type": "event",
        },
        {
            "anonymous": False,
            "inputs": [
                {"indexed": False, "internalType": "bytes32", "name": "b", "type": "bytes32"},
                {"indexed": False, "internalType": "uint256", "name": "prevNum", "type": "uint256"},
                {"indexed": False, "internalType": "string", "name": "dynData", "type": "string"},
                {"indexed": True, "internalType": "uint256", "name": "newNum", "type": "uint256"},
                {"indexed": True, "internalType": "string", "name": "dynIndexed", "type": "string"},
            ],
            "name": "NumberChange",
            "type": "event",
        },
        {
            "inputs": [],
            "name": "myNumber",
            "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
            "stateMutability": "view",
            "type": "function",
        }
        # [...]
    ]

    address = solidity_contract_instance.address

    contract = Contract(address, abi=abi_list)

    assert isinstance(contract, ContractInstance)
    assert contract.address == address
    assert contract.myNumber() == 0


def test_load_contract_from_file(solidity_contract_instance):
    """
    need feedback about the json file specifications
    """
    PROJECT_PATH = Path(__file__).parent
    CONTRACTS_FOLDER = PROJECT_PATH / "data" / "contracts" / "ethereum"
    json_abi_file = f"{CONTRACTS_FOLDER}/solidity_contract_json.json"

    address = solidity_contract_instance.address
    contract = Contract(address, abi=json_abi_file)

    assert isinstance(contract, ContractInstance)
    assert contract.address == address
    assert contract.myNumber() == 0
