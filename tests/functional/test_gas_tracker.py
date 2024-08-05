def test_append_gas(gas_tracker, owner, vyper_contract_instance, eth_tester_provider):
    tx = vyper_contract_instance.setNumber(924, sender=owner)
    trace = tx.trace
    gas_tracker.append_gas(trace, vyper_contract_instance.address)
    report = gas_tracker.session_gas_report
    contract_name = vyper_contract_instance.contract_type.name
    assert contract_name in report
    assert "setNumber" in report[contract_name]
    assert tx.gas_used in report[contract_name]["setNumber"]


def test_append_gas_deploy(gas_tracker, vyper_contract_instance):
    tx = vyper_contract_instance.creation_metadata.receipt
    trace = tx.trace
    gas_tracker.append_gas(trace, vyper_contract_instance.address)
    report = gas_tracker.session_gas_report
    contract_name = vyper_contract_instance.contract_type.name
    assert contract_name in report
    assert "__new__" in report[contract_name]
    assert tx.gas_used in report[contract_name]["__new__"]


def test_append_gas_transfer(gas_tracker, sender, receiver):
    tx = sender.transfer(receiver, 0)
    trace = tx.trace
    gas_tracker.append_gas(trace, receiver.address)
    report = gas_tracker.session_gas_report

    # ETH-transfers are not included in the final report.
    assert report is None
