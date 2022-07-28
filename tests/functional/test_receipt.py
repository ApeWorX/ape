import pytest

from ape.api import ReceiptAPI
from ape.exceptions import OutOfGasError
from ape_ethereum.transactions import Receipt, TransactionStatusEnum


@pytest.fixture
def invoke_receipt(vyper_contract_instance, owner):
    return vyper_contract_instance.setNumber(1, sender=owner)


def test_show_trace(invoke_receipt):
    # For better tests, see a provider plugin that supports this RPC,
    # such as ape-hardhat.
    with pytest.raises(NotImplementedError):
        invoke_receipt.show_trace()


def test_decode_logs_specify_abi(invoke_receipt, vyper_contract_instance):
    abi = vyper_contract_instance.NumberChange.abi
    logs = [log for log in invoke_receipt.decode_logs(abi=abi)]
    assert len(logs) == 1
    assert logs[0].newNum == 1
    assert logs[0].event_name == "NumberChange"
    assert logs[0].log_index == 0
    assert logs[0].transaction_index == 0


def test_decode_logs_specify_abi_as_event(
    mocker, invoke_receipt, vyper_contract_instance, eth_tester_provider
):
    spy = mocker.spy(eth_tester_provider.web3.eth, "get_logs")
    abi = vyper_contract_instance.NumberChange
    logs = [log for log in invoke_receipt.decode_logs(abi=abi)]
    assert len(logs) == 1
    assert logs[0].newNum == 1
    assert logs[0].event_name == "NumberChange"
    assert logs[0].log_index == 0
    assert logs[0].transaction_index == 0

    # Tests against a bug where the API was called unnecessarily
    assert spy.call_count == 0


def test_decode_logs_with_ds_notes(ds_note_test_contract, owner):
    contract = ds_note_test_contract
    receipt = contract.test_0(sender=owner)
    logs = [log for log in receipt.decode_logs()]
    assert len(logs) == 1
    assert logs[0].event_name == "foo"
    assert logs[0].log_index == 0
    assert logs[0].transaction_index == 0

    receipt = contract.test_1(sender=owner)
    logs = [log for log in receipt.decode_logs()]
    assert len(logs) == 1
    assert logs[0].event_name == "foo"
    assert logs[0].event_arguments == {"a": 1}
    assert logs[0].log_index == 0
    assert logs[0].transaction_index == 0

    receipt = contract.test_2(sender=owner)
    logs = [log for log in receipt.decode_logs()]
    assert len(logs) == 1
    assert logs[0].event_name == "foo"
    assert logs[0].event_arguments == {"a": 1, "b": 2}
    assert logs[0].log_index == 0
    assert logs[0].transaction_index == 0

    receipt = contract.test_3(sender=owner)
    logs = [log for log in receipt.decode_logs()]
    assert len(logs) == 1
    assert logs[0].event_name == "foo"
    assert logs[0].event_arguments == {"a": 1, "b": 2, "c": 3}
    assert logs[0].log_index == 0
    assert logs[0].transaction_index == 0


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


def test_decode_logs_unspecified_abi_gets_all_logs(owner, contract_instance):
    receipt = contract_instance.fooAndBar(sender=owner)
    logs = [log for log in receipt.decode_logs()]
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


def test_receipt_raise_for_status_out_of_gas_error(mocker):
    gas_limit = 100000
    receipt = Receipt(
        provider=mocker.MagicMock(),
        txn_hash="",
        gas_used=gas_limit,
        gas_limit=gas_limit,
        status=TransactionStatusEnum.FAILING,
        gas_price=0,
        block_number=0,
        sender="",
        receiver="",
        nonce=0,
    )
    with pytest.raises(OutOfGasError):
        receipt.raise_for_status()
