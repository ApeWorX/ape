import pytest


@pytest.fixture
def invoke_receipt(vyper_contract_instance, owner):
    return vyper_contract_instance.setNumber(1, sender=owner)


def test_show_trace(invoke_receipt):
    # For better tests, see a provider plugin that supports this RPC,
    # such as ape-hardhat.
    with pytest.raises(NotImplementedError):
        invoke_receipt.show_trace()


def test_decode_logs(invoke_receipt):
    logs = [log for log in invoke_receipt.decode_logs()]
    assert len(logs) == 1
    assert logs[0].newNum == 1


def test_decode_logs_specify_abi(invoke_receipt, vyper_contract_instance):
    abi = vyper_contract_instance.NumberChange.abi
    logs = [log for log in invoke_receipt.decode_logs(abi=abi)]
    assert len(logs) == 1
    assert logs[0].newNum == 1


def test_decode_logs_specify_abi_as_event(invoke_receipt, vyper_contract_instance):
    abi = vyper_contract_instance.NumberChange
    logs = [log for log in invoke_receipt.decode_logs(abi=abi)]
    assert len(logs) == 1
    assert logs[0].newNum == 1


def test_decode_logs_with_ds_notes(ds_note_test_contract, owner):
    contract = ds_note_test_contract
    receipt = contract.test_0(sender=owner)
    logs = [log for log in receipt.decode_logs()]
    assert len(logs) == 1
    assert logs[0].name == "foo"

    receipt = contract.test_1(sender=owner)
    logs = [log for log in receipt.decode_logs()]
    assert len(logs) == 1
    assert logs[0].name == "foo"
    assert logs[0].event_arguments == {"a": 1}

    receipt = contract.test_2(sender=owner)
    logs = [log for log in receipt.decode_logs()]
    assert len(logs) == 1
    assert logs[0].name == "foo"
    assert logs[0].event_arguments == {"a": 1, "b": 2}

    receipt = contract.test_3(sender=owner)
    logs = [log for log in receipt.decode_logs()]
    assert len(logs) == 1
    assert logs[0].name == "foo"
    assert logs[0].event_arguments == {"a": 1, "b": 2, "c": 3}
