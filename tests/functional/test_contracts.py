import pytest

from ape import Contract
from ape.api import Address, ReceiptAPI
from ape.exceptions import DecodingError
from ape.types import ContractLog


def test_init_at_unknown_address():
    address = "0x274b028b03A250cA03644E6c578D81f019eE1323"
    contract = Contract(address)
    assert type(contract) == Address
    assert contract.address == address


def test_contract_logs_from_receipts(owner, contract_instance):
    event_type = contract_instance.NumberChange

    # Invoke a transaction 3 times that generates 3 logs.
    receipt_0 = contract_instance.set_number(1, sender=owner)
    receipt_1 = contract_instance.set_number(2, sender=owner)
    receipt_2 = contract_instance.set_number(3, sender=owner)

    def assert_receipt_logs(receipt: ReceiptAPI, num: int):
        logs = [log for log in event_type.from_receipt(receipt)]
        assert len(logs) == 1
        assert_log_values(logs[0], num)

    assert_receipt_logs(receipt_0, 1)
    assert_receipt_logs(receipt_1, 2)
    assert_receipt_logs(receipt_2, 3)


def test_contract_logs_from_event_type(contract_instance, owner):
    event_type = contract_instance.NumberChange

    contract_instance.set_number(1, sender=owner)
    contract_instance.set_number(2, sender=owner)
    contract_instance.set_number(3, sender=owner)

    logs = [log for log in event_type]
    assert len(logs) == 3
    assert_log_values(logs[0], 1)
    assert_log_values(logs[1], 2)
    assert_log_values(logs[2], 3)


def test_contract_logs_from_filter(contract_instance, owner):
    contract_instance.set_number(1, sender=owner)
    logs = [log for log in contract_instance.NumberChange.filter(new_num=1)]
    assert len(logs) == 1
    assert_log_values(logs[0], 1)


def test_contract_logs_from_non_indexed_filter(contract_instance, owner):
    contract_instance.set_number(1, sender=owner)
    with pytest.raises(DecodingError):
        _ = [log for log in contract_instance.NumberChange.filter(prev_num=1)]


def assert_log_values(log: ContractLog, number: int):
    assert log.prev_num == number - 1
    assert log.new_num == number
