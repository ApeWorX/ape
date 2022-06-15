import shutil
from pathlib import Path

import pytest
from ethpm_types import ContractType
from evm_trace import CallTreeNode
from rich import print as rich_print

from ape.contracts import ContractContainer
from ape.utils.trace import CallTraceParser
from ape_ethereum.transactions import Receipt, TransactionStatusEnum
from tests.functional.data.python import CALL_TREE_DICT

BASE_CONTRACTS_PATH = Path(__file__).parent.parent / "data" / "contracts" / "ethereum"


@pytest.fixture(autouse=True, scope="module")
def local_contracts(owner, networks_connected_to_tester):
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
def full_contracts_cache(config):
    destination = config.DATA_FOLDER / "ethereum"
    shutil.copytree(BASE_CONTRACTS_PATH, destination)


@pytest.fixture(scope="module")
def eth_receipt():
    raw_receipt = {
        "block_number": 14968261,
        "data": b"7-\xca\x07",
        "gas_limit": 492533,
        "gas_price": 0,
        "gas_used": 469604,
        "logs": [],
        "nonce": 3,
        "receiver": "0xF2Df0b975c0C9eFa2f8CA0491C2d1685104d2488",
        "required_confirmations": 0,
        "sender": "0x1e59ce931B4CFea3fe4B875411e280e173cB7A9C",
        "status": TransactionStatusEnum.NO_ERROR,
        "txn_hash": "0x43abb1fdadfdae68f84ce8cd2582af6ab02412f686ee2544aa998db662a5ef50",
        "value": 123,
    }
    return Receipt.parse_obj(raw_receipt)


@pytest.fixture(scope="module")
def call_tree():
    return CallTreeNode.parse_obj(CALL_TREE_DICT)


def test_get_call_trace_using_locally_deployed_contracts(
    eth_receipt, call_tree, caplog, local_contracts
):
    parser = CallTraceParser(eth_receipt)
    actual = parser.parse_as_tree(call_tree)
    rich_print(actual)
    breakpoint()
