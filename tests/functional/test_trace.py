import json
import re

import pytest
from evm_trace import CallTreeNode, CallType
from hexbytes import HexBytes

from ape_ethereum.trace import CallTrace, Trace, TransactionTrace, parse_rich_tree
from tests.functional.data.python import (
    TRACE_MISSING_GAS,
    TRACE_WITH_CUSTOM_ERROR,
    TRACE_WITH_SUB_CALLS,
)

# Used foundry to retrieve this partity-style trace data.
FAILING_TRACE = {
    "call_type": "CALL",
    "address": "0x5fbdb2315678afecb367f032d93f642f64180aa3",
    "value": 0,
    "depth": 0,
    "gas_limit": 30000000,
    "gas_cost": 2524,
    "calldata": "0x3fb5c1cb0000000000000000000000000000000000000000000000000000000000000141",
    "returndata": "0x08c379a00000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000000000000000000b21617574686f72697a6564000000000000000000000000000000000000000000",  # noqa: E501
    "calls": [],
    "selfdestruct": False,
    "failed": True,
}
PASSING_TRACE = {
    "call_type": "CALL",
    "address": "0x5fbdb2315678afecb367f032d93f642f64180aa3",
    "value": 0,
    "depth": 0,
    "gas_limit": 30000000,
    "gas_cost": 32775,
    "calldata": "0x3fb5c1cb0000000000000000000000000000000000000000000000000000000000000141",  # noqa: E501
    "returndata": "0x",
    "calls": [],
    "selfdestruct": False,
    "failed": False,
}
PASSING_TRACE_LARGE = json.loads(TRACE_WITH_SUB_CALLS)
FAILING_TRACE_WITH_CUSTOM_ERROR = json.loads(TRACE_WITH_CUSTOM_ERROR)
PASSING_TRACE_MISSING_GAS = json.loads(TRACE_MISSING_GAS)
TRACE_API_DATA = {
    "call_trace_approach": 1,
    "transaction_hash": "0xb7d7f1d5ce7743e821d3026647df486f517946ef1342a1ae93c96e4a8016eab7",
    "debug_trace_transaction_parameters": {"stepsTracing": True, "enableMemory": True},
}


@pytest.fixture
def simple_trace_cls():
    def fn(call, tx=None):
        class SimpleTrace(Trace):
            def get_calltree(self) -> CallTreeNode:
                return CallTreeNode.model_validate(call)

            @property
            def raw_trace_frames(self):
                return []

            @property
            def transaction(self) -> dict:
                return tx or {}

        return SimpleTrace

    return fn


def test_parse_rich_tree(vyper_contract_instance):
    """
    Show that when full selector is set as the method ID,
    the tree-output only shows the short method name.
    """
    contract_id = vyper_contract_instance.contract_type.name
    method_id = vyper_contract_instance.contract_type.methods["setAddress"].selector
    call = CallTreeNode(address=vyper_contract_instance.address, call_type=CallType.CALL)
    data = {
        **call.model_dump(by_alias=True, mode="json"),
        "method_id": method_id,
        "contract_id": contract_id,
    }
    actual = parse_rich_tree(data).label
    expected = f"[#ff8c00]{contract_id}[/].[bright_green]setAddress[/]()"
    assert actual == expected


def test_get_gas_report(gas_tracker, owner, vyper_contract_instance):
    tx = vyper_contract_instance.setNumber(924, sender=owner)
    trace = tx.trace
    actual = trace.get_gas_report()
    contract_name = vyper_contract_instance.contract_type.name
    expected = {contract_name: {"setNumber": [tx.gas_used]}}
    assert actual == expected


def test_get_gas_report_deploy(gas_tracker, vyper_contract_instance):
    tx = vyper_contract_instance.creation_metadata.receipt
    trace = tx.trace
    actual = trace.get_gas_report()
    contract_name = vyper_contract_instance.contract_type.name
    expected = {contract_name: {"__new__": [tx.gas_used]}}
    assert actual == expected


def test_get_gas_report_transfer(gas_tracker, sender, receiver):
    tx = sender.transfer(receiver, 0)
    trace = tx.trace
    actual = trace.get_gas_report()
    expected = {"__ETH_transfer__": {"to:TEST::2": [tx.gas_used]}}
    assert actual == expected


def test_get_gas_report_with_sub_calls(simple_trace_cls):
    trace_cls = simple_trace_cls(PASSING_TRACE_LARGE)
    trace = trace_cls.model_validate(TRACE_API_DATA)
    actual = trace.get_gas_report()
    assert len(actual) > 1  # Sub-contract calls!


def test_transaction_trace_create(vyper_contract_instance):
    tx_hash = vyper_contract_instance.creation_metadata.txn_hash
    trace = TransactionTrace(transaction_hash=tx_hash)
    actual = f"{trace}"
    expected = r"VyperContract\.__new__\(num=0\) \[\d+ gas\]"
    assert re.match(expected, actual)


def test_transaction_trace_multiline(vyper_contract_instance, owner):
    tx = vyper_contract_instance.getNestedAddressArray.transact(sender=owner)
    actual = f"{tx.trace}"
    expected = r"""
VyperContract\.getNestedAddressArray\(\) -> \[
    \['tx\.origin', 'tx\.origin', 'tx\.origin'\],
    \['ZERO_ADDRESS', 'ZERO_ADDRESS', 'ZERO_ADDRESS'\]
\] \[\d+ gas\]
"""
    assert re.match(expected.strip(), actual.strip())


def test_transaction_trace_list_of_lists(vyper_contract_instance, owner):
    tx = vyper_contract_instance.getNestedArrayMixedDynamic.transact(sender=owner)
    actual = f"{tx.trace}"
    expected = r"""
VyperContract\.getNestedArrayMixedDynamic\(\) -> \[
    \[\[\[0\], \[0, 1\], \[0, 1, 2\]\]\],
    \[
        \[\[0\], \[0, 1\], \[0, 1, 2\]\],
        \[\[0\], \[0, 1\], \[0, 1, 2\]\]
    \],
    \[\],
    \[\],
    \[\]
\] \[\d+ gas\]
"""
    assert re.match(expected.strip(), actual.strip())


def test_call_trace_debug_trace_call_not_supported(owner, vyper_contract_instance):
    """
    When using EthTester, we can still see the top-level trace of a call.
    """
    tx = {"to": vyper_contract_instance.address, "from": owner.address}
    trace = CallTrace(tx=tx)
    actual = f"{trace}"
    assert actual == "VyperContract.0x()"


def test_revert_message(simple_trace_cls):
    trace_cls = simple_trace_cls(FAILING_TRACE)
    trace = trace_cls.model_validate(TRACE_API_DATA)
    expected = "!authorized"
    assert trace.revert_message == expected


def test_revert_message_passing_trace(simple_trace_cls):
    trace_cls = simple_trace_cls(PASSING_TRACE)
    trace = trace_cls.model_validate(TRACE_API_DATA)
    assert trace.revert_message is None  # didn't revert


def test_revert_message_custom_error(simple_trace_cls, setup_custom_error):
    address = "0x3fC91A3afd70395Cd496C647d5a6CC9D4B2b7FAD"
    setup_custom_error(address)
    trace_cls = simple_trace_cls(FAILING_TRACE_WITH_CUSTOM_ERROR)
    trace = trace_cls.model_validate(TRACE_API_DATA)
    expected = "AllowanceExpired(deadline=0)"
    assert trace.revert_message == expected


def test_enriched_calltree_adds_missing_gas(simple_trace_cls):
    compute_gas = 1234
    base_gas = 21_000
    data_gas = 64  # 4 gas per 0-byte and 16 gas per non-zero byte
    total_gas = compute_gas + base_gas + data_gas

    trace_cls = simple_trace_cls(
        PASSING_TRACE_MISSING_GAS, tx={"gas_used": total_gas, "data": HexBytes("0x12345678")}
    )
    trace = trace_cls.model_validate(TRACE_API_DATA)
    actual = trace.enriched_calltree
    assert actual["gas_cost"] == compute_gas
