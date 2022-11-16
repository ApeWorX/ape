from dataclasses import dataclass
from pathlib import Path

import pytest
from ethpm_types import ContractType
from evm_trace import CallTreeNode
from rich import print as rich_print

from ape.contracts import ContractContainer
from ape.utils.trace import CallTraceParser
from ape_ethereum.transactions import BaseTransaction, Receipt
from tests.functional.data.python import (
    LOCAL_CALL_TREE_DICT,
    MAINNET_CALL_TREE_DICT,
    MAINNET_RECEIPT_DICT,
)
from tests.functional.utils.expected_traces import LOCAL_TRACE, MAINNET_TRACE

FAILED_TXN_HASH = "0x053cba5c12172654d894f66d5670bab6215517a94189a9ffc09bc40a589ec04d"
INTERNAL_TRANSFERS_TXN_HASH_0 = "0xb7d7f1d5ce7743e821d3026647df486f517946ef1342a1ae93c96e4a8016eab7"
INTERNAL_TRANSFERS_TXN_HASH_1 = "0x0537316f37627655b7fe5e50e23f71cd835b377d1cde4226443c94723d036e32"
BASE_CONTRACTS_PATH = Path(__file__).parent.parent / "data" / "contracts" / "ethereum"


@pytest.fixture
def local_contracts(owner, eth_tester_provider):
    containers = {}
    for char in ("a", "b", "c"):
        contract_data = BASE_CONTRACTS_PATH / "local" / f"contract_{char}.json"
        contract_type = ContractType.parse_raw(contract_data.read_text())
        container = ContractContainer(contract_type)
        containers[char] = container

    contract_c = owner.deploy(containers["c"])
    contract_b = owner.deploy(containers["b"], contract_c.address)
    contract_a = owner.deploy(containers["a"], contract_b.address, contract_c.address)
    return contract_a, contract_b, contract_c


@pytest.fixture(autouse=True, scope="module")
def full_contracts_cache(chain):
    # Copy mainnet contract types into local cache to make them accessible for look-up
    mainnet_contracts_dir = BASE_CONTRACTS_PATH / "mainnet"
    for contract_type_file in mainnet_contracts_dir.iterdir():
        address = contract_type_file.stem
        contract_type = ContractType.parse_raw(contract_type_file.read_text())
        chain.contracts._local_contract_types[address] = contract_type


@pytest.fixture
def local_receipt(local_contracts, owner):
    return local_contracts[0].methodWithoutArguments(sender=owner, value=123)


@pytest.fixture(scope="module")
def mainnet_receipt():
    txn = BaseTransaction.parse_obj(MAINNET_RECEIPT_DICT["transaction"])
    MAINNET_RECEIPT_DICT["transaction"] = txn
    return Receipt.parse_obj(MAINNET_RECEIPT_DICT)


@pytest.fixture
def local_call_tree(local_contracts):
    def set_address(d):
        if d["address"] == "b":
            d["address"] = local_contracts[1].address
        elif d["address"] == "c":
            d["address"] = local_contracts[2].address

    new_dict = dict(LOCAL_CALL_TREE_DICT)
    new_dict["address"] = local_contracts[0].address

    def set_all_addresses(d):
        set_address(d)
        for call in d["calls"]:
            set_all_addresses(call)

    set_all_addresses(new_dict)
    return CallTreeNode.parse_obj(new_dict)


@pytest.fixture(scope="module")
def mainnet_call_tree():
    return CallTreeNode.parse_obj(MAINNET_CALL_TREE_DICT)


@pytest.fixture(params=("local", "mainnet"))
def case(request, local_receipt, mainnet_receipt, local_call_tree, mainnet_call_tree):
    @dataclass
    class TraceTestCase:
        receipt: Receipt
        expected: str
        call_tree: CallTreeNode
        name: str = request.param

    # Add more test trace cases here
    if request.param == "local":
        return TraceTestCase(local_receipt, LOCAL_TRACE, local_call_tree)
    elif request.param == "mainnet":
        return TraceTestCase(mainnet_receipt, MAINNET_TRACE, mainnet_call_tree)


@pytest.fixture
def assert_trace(capsys):
    def assert_trace(actual: str):
        output, _ = capsys.readouterr()
        trace = [s.strip() for s in output.split("\n")]

        for line in trace:
            parts = line.split(" ")
            for part in [p.strip() for p in parts if p.strip()]:
                part = part.strip()
                assert part in actual, f"Could not find '{part}' in expected\n{output}"

    return assert_trace


def test_trace(case, assert_trace):
    parser = CallTraceParser(sender=case.receipt.sender, transaction_hash=case.receipt.txn_hash)
    actual = parser.parse_as_tree(case.call_tree)
    rich_print(actual)
    assert_trace(case.expected)
