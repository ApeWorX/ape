import json
from pathlib import Path

from ape import Contract
from ape.contracts import ContractInstance


def test_contract_from_abi(contract_instance):
    contract = Contract(contract_instance.address, abi=contract_instance.contract_type.abi)
    assert isinstance(contract, ContractInstance)
    assert contract.address == contract_instance.address
    assert contract.myNumber() == 0
    assert contract.balance == 0


def test_contract_from_abi_list(contract_instance):
    contract = Contract(
        contract_instance.address, abi=[abi.dict() for abi in contract_instance.contract_type.abi]
    )

    assert isinstance(contract, ContractInstance)
    assert contract.address == contract_instance.address
    assert contract.myNumber() == 0


def test_contract_from_json_str(contract_instance):
    contract = Contract(
        contract_instance.address,
        abi=json.dumps([abi.dict() for abi in contract_instance.contract_type.abi]),
    )

    assert isinstance(contract, ContractInstance)
    assert contract.address == contract_instance.address
    assert contract.myNumber() == 0


def test_contract_from_file(contract_instance):
    """
    need feedback about the json file specifications
    """
    PROJECT_PATH = Path(__file__).parent
    CONTRACTS_FOLDER = PROJECT_PATH / "data" / "contracts" / "ethereum" / "abi"
    json_abi_file = f"{CONTRACTS_FOLDER}/contract_abi.json"

    address = contract_instance.address
    contract = Contract(address, abi=json_abi_file)

    assert isinstance(contract, ContractInstance)
    assert contract.address == address
    assert contract.myNumber() == 0
