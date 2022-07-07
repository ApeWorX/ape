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
