import re

from evm_trace import CallTreeNode, CallType

from ape_ethereum.trace import CallTrace, TransactionTrace, parse_rich_tree


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


def test_transaction_trace_create(vyper_contract_instance):
    trace = TransactionTrace(transaction_hash=vyper_contract_instance.creation_metadata.txn_hash)
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
