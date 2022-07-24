import pytest

from ape.api import ReceiptAPI


@pytest.fixture
def invoke_receipt(solidity_contract_instance, owner):
    return solidity_contract_instance.setNumber(1, sender=owner)


def test_show_trace(invoke_receipt):
    # For better tests, see a provider plugin that supports this RPC,
    # such as ape-hardhat.
    with pytest.raises(NotImplementedError):
        invoke_receipt.show_trace()


def test_decode_logs(owner, contract_instance, assert_log_values):
    event_type = contract_instance.NumberChange

    # Invoke a transaction 3 times that generates 3 logs.
    receipt_0 = contract_instance.setNumber(1, sender=owner)
    receipt_1 = contract_instance.setNumber(2, sender=owner)
    receipt_2 = contract_instance.setNumber(3, sender=owner)

    def assert_receipt_logs(receipt: ReceiptAPI, num: int):
        logs = [log for log in receipt.decode_logs(event_type)]
        assert len(logs) == 1
        assert_log_values(logs[0], num)

    assert_receipt_logs(receipt_0, 1)
    assert_receipt_logs(receipt_1, 2)
    assert_receipt_logs(receipt_2, 3)


def test_decode_logs_multiple_event_types(owner, contract_instance, assert_log_values):
    foo_happened = contract_instance.FooHappened
    bar_happened = contract_instance.BarHappened
    receipt = contract_instance.fooAndBar(sender=owner)
    logs = [log for log in receipt.decode_logs([foo_happened, bar_happened])]
    assert len(logs) == 2
    assert logs[0].foo == 0
    assert logs[1].bar == 1


def test_get_failed_receipt(owner, vyper_contract_instance, eth_tester_provider):
    # Setting to '5' always fails.
    transaction = vyper_contract_instance.setNumber.as_transaction(
        5, sender=owner, gas_limit=100000
    )
    receipt = owner.call(transaction)
    assert receipt.failed
