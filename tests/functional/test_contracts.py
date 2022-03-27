from typing import Optional

import pytest

from ape import Contract
from ape.api import Address, ReceiptAPI
from ape.exceptions import DecodingError
from ape.types import ContractLog

CONTRACT_ADDRESS = "0x274b028b03A250cA03644E6c578D81f019eE1323"


def test_init_at_unknown_address():
    contract = Contract(CONTRACT_ADDRESS)
    assert type(contract) == Address
    assert contract.address == CONTRACT_ADDRESS


def test_deploy(sender, contract_container):
    contract = contract_container.deploy(sender=sender)
    assert contract.address == CONTRACT_ADDRESS


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

        # Also verify can we logs the other way
        logs = [log for log in receipt.decode_logs(event_type)]
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
    assert len(logs) == 3, "Unexpected number of logs"
    assert_log_values(logs[0], 1)
    assert_log_values(logs[1], 2)
    assert_log_values(logs[2], 3)


def test_contract_logs_index_access(contract_instance, owner):
    event_type = contract_instance.NumberChange

    contract_instance.set_number(1, sender=owner)
    contract_instance.set_number(2, sender=owner)
    contract_instance.set_number(3, sender=owner)

    assert_log_values(event_type[0], 1)
    assert_log_values(event_type[1], 2)
    assert_log_values(event_type[2], 3)

    # Verify negative index access
    assert_log_values(event_type[-3], 1)
    assert_log_values(event_type[-2], 2)
    assert_log_values(event_type[-1], 3)


def test_contract_logs_splicing(contract_instance, owner):
    event_type = contract_instance.NumberChange

    contract_instance.set_number(1, sender=owner)
    contract_instance.set_number(2, sender=owner)
    contract_instance.set_number(3, sender=owner)

    logs = event_type[:2]
    assert len(logs) == 2
    assert_log_values(logs[0], 1)
    assert_log_values(logs[1], 2)

    logs = event_type[2:]
    assert len(logs) == 1
    assert_log_values(logs[0], 3)

    log = event_type[1]
    assert_log_values(log, 2)


def test_contract_logs_range(contract_instance, owner):
    contract_instance.set_number(1, sender=owner)
    logs = [
        log for log in contract_instance.NumberChange.range(100, event_parameters={"new_num": 1})
    ]
    assert len(logs) == 1, "Unexpected number of logs"
    assert_log_values(logs[0], 1)


def test_contract_logs_range_start_and_stop(contract_instance, owner, chain):
    # Create 1 event
    contract_instance.set_number(1, sender=owner)

    # Grab start block after first event
    start_block = chain.blocks.height

    contract_instance.set_number(2, sender=owner)
    contract_instance.set_number(3, sender=owner)

    stop = 30  # Stop can be bigger than height, it doesn't not matter
    logs = [log for log in contract_instance.NumberChange.range(start_block, stop=stop)]
    assert len(logs) == 3, "Unexpected number of logs"


def test_contract_logs_range_only_stop(contract_instance, owner, chain):
    # Create 1 event
    contract_instance.set_number(1, sender=owner)
    contract_instance.set_number(2, sender=owner)
    contract_instance.set_number(3, sender=owner)

    stop = 100  # Stop can be bigger than height, it doesn't not matter
    logs = [log for log in contract_instance.NumberChange.range(stop)]
    assert len(logs) == 3, "Unexpected number of logs"


def test_contract_logs_range_with_paging(contract_instance, owner, chain):
    # Create 1 log each in the first 3 blocks.
    for i in range(3):
        contract_instance.set_number(i + 1, sender=owner)

    # Mine 3 times to ensure we can handle uneventful blocks.
    for i in range(3):
        chain.mine()

    # Create one more log after the empty blocks.
    contract_instance.set_number(100, sender=owner)

    logs = [log for log in contract_instance.NumberChange.range(100, block_page_size=1)]
    assert len(logs) == 4, "Unexpected number of logs"
    assert_log_values(logs[0], 1)
    assert_log_values(logs[1], 2)
    assert_log_values(logs[2], 3)
    assert_log_values(logs[3], 100, previous_number=3)


def test_contract_logs_range_over_paging(contract_instance, owner, chain):
    # Create 1 log each in the first 3 blocks.
    for i in range(3):
        contract_instance.set_number(i + 1, sender=owner)

    # 50 is way more than 3 but it shouldn't matter.
    logs = [log for log in contract_instance.NumberChange.range(100, block_page_size=50)]
    assert len(logs) == 3, "Unexpected number of logs"


def test_contract_logs_from_non_indexed_range(contract_instance, owner):
    contract_instance.set_number(1, sender=owner)
    with pytest.raises(DecodingError):
        _ = [
            log for log in contract_instance.NumberChange.range(0, event_parameters={"prev_num": 1})
        ]


def assert_log_values(log: ContractLog, number: int, previous_number: Optional[int] = None):
    expected_previous_number = number - 1 if previous_number is None else previous_number
    assert log.prev_num == expected_previous_number, "Event param 'prev_num' has unexpected value"
    assert log.new_num == number, "Event param 'new_num' has unexpected value"
