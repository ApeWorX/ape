from tests.conftest import geth_process_test


@geth_process_test
def test_append_gas(gas_tracker, geth_account, geth_contract):
    tx = geth_contract.setNumber(924, sender=geth_account)
    trace = tx.trace
    gas_tracker.append_gas(trace, geth_contract.address)
    report = gas_tracker.session_gas_report
    contract_name = geth_contract.contract_type.name
    assert contract_name in report
    assert "setNumber" in report[contract_name]
    assert tx.gas_used in report[contract_name]["setNumber"]


@geth_process_test
def test_append_gas_deploy(gas_tracker, geth_contract):
    tx = geth_contract.creation_metadata.receipt
    trace = tx.trace
    gas_tracker.append_gas(trace, geth_contract.address)
    report = gas_tracker.session_gas_report
    expected = {geth_contract.contract_type.name: {"__new__": [tx.gas_used]}}
    assert report == expected
