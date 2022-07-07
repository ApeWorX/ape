from queue import Queue

import pytest

from ape.api import ReceiptAPI
from ape.exceptions import DecodingError


def test_contract_logs_from_receipts(owner, contract_instance, assert_log_values):
    event_type = contract_instance.NumberChange

    # Invoke a transaction 3 times that generates 3 logs.
    receipt_0 = contract_instance.setNumber(1, sender=owner)
    receipt_1 = contract_instance.setNumber(2, sender=owner)
    receipt_2 = contract_instance.setNumber(3, sender=owner)

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


def test_contract_logs_from_event_type(contract_instance, owner, assert_log_values):
    event_type = contract_instance.NumberChange

    contract_instance.setNumber(1, sender=owner)
    contract_instance.setNumber(2, sender=owner)
    contract_instance.setNumber(3, sender=owner)

    logs = [log for log in event_type]
    assert len(logs) == 3, "Unexpected number of logs"
    assert_log_values(logs[0], 1)
    assert_log_values(logs[1], 2)
    assert_log_values(logs[2], 3)


def test_contract_logs_index_access(contract_instance, owner, assert_log_values):
    event_type = contract_instance.NumberChange

    contract_instance.setNumber(1, sender=owner)
    contract_instance.setNumber(2, sender=owner)
    contract_instance.setNumber(3, sender=owner)

    assert_log_values(event_type[0], 1)
    assert_log_values(event_type[1], 2)
    assert_log_values(event_type[2], 3)

    # Verify negative index access
    assert_log_values(event_type[-3], 1)
    assert_log_values(event_type[-2], 2)
    assert_log_values(event_type[-1], 3)


def test_contract_logs_splicing(contract_instance, owner, assert_log_values):
    event_type = contract_instance.NumberChange

    contract_instance.setNumber(1, sender=owner)
    contract_instance.setNumber(2, sender=owner)
    contract_instance.setNumber(3, sender=owner)

    logs = event_type[:2]
    assert len(logs) == 2
    assert_log_values(logs[0], 1)
    assert_log_values(logs[1], 2)

    logs = event_type[2:]
    assert len(logs) == 1
    assert_log_values(logs[0], 3)

    log = event_type[1]
    assert_log_values(log, 2)


def test_contract_logs_range(contract_instance, owner, assert_log_values):
    contract_instance.setNumber(1, sender=owner)
    logs = [
        log for log in contract_instance.NumberChange.range(100, event_parameters={"newNum": 1})
    ]
    assert len(logs) == 1, "Unexpected number of logs"
    assert_log_values(logs[0], 1)


def test_contract_logs_range_by_address(
    mocker, eth_tester_provider, test_accounts, contract_instance, owner, assert_log_values
):
    spy = mocker.spy(eth_tester_provider.web3.eth, "get_logs")
    contract_instance.setAddress(test_accounts[1], sender=owner)
    logs = [
        log
        for log in contract_instance.AddressChange.range(
            100, event_parameters={"newAddress": test_accounts[1]}
        )
    ]

    # NOTE: This spy assertion tests against a bug where address queries were not
    # 0x-prefixed. However, this was still valid in EthTester and thus was not causing
    # test failures.
    spy.assert_called_once_with(
        {
            "address": [contract_instance.address],
            "fromBlock": 0,
            "toBlock": 3,
            "topics": [
                "0x7ff7bacc6cd661809ed1ddce28d4ad2c5b37779b61b9e3235f8262be529101a9",
                "0x000000000000000000000000c89d42189f0450c2b2c3c61f58ec5d628176a1e7",
            ],
        }
    )
    assert len(logs) == 1
    assert logs[0].newAddress == test_accounts[1]


def test_contracts_log_multiple_addresses(
    contract_instance, contract_container, owner, assert_log_values
):
    another_instance = contract_container.deploy(sender=owner)
    contract_instance.setNumber(1, sender=owner)
    another_instance.setNumber(1, sender=owner)

    logs = [
        log
        for log in contract_instance.NumberChange.range(
            100, event_parameters={"newNum": 1}, extra_addresses=[another_instance.address]
        )
    ]
    assert len(logs) == 2, "Unexpected number of logs"
    assert_log_values(logs[0], 1)
    assert_log_values(logs[1], 1)


def test_contract_logs_range_start_and_stop(contract_instance, owner, chain):
    # Create 1 event
    contract_instance.setNumber(1, sender=owner)

    # Grab start block after first event
    start_block = chain.blocks.height

    contract_instance.setNumber(2, sender=owner)
    contract_instance.setNumber(3, sender=owner)

    stop = 30  # Stop can be bigger than height, it doesn't not matter
    logs = [log for log in contract_instance.NumberChange.range(start_block, stop=stop)]
    assert len(logs) == 3, "Unexpected number of logs"


def test_contract_logs_range_only_stop(contract_instance, owner, chain):
    # Create 1 event
    contract_instance.setNumber(1, sender=owner)
    contract_instance.setNumber(2, sender=owner)
    contract_instance.setNumber(3, sender=owner)

    stop = 100  # Stop can be bigger than height, it doesn't not matter
    logs = [log for log in contract_instance.NumberChange.range(stop)]
    assert len(logs) == 3, "Unexpected number of logs"


def test_contract_logs_range_with_paging(contract_instance, owner, chain, assert_log_values):
    # Create 1 log each in the first 3 blocks.
    for i in range(3):
        contract_instance.setNumber(i + 1, sender=owner)

    # Mine 3 times to ensure we can handle uneventful blocks.
    for i in range(3):
        chain.mine()

    # Create one more log after the empty blocks.
    contract_instance.setNumber(100, sender=owner)

    logs = [log for log in contract_instance.NumberChange.range(100, block_page_size=1)]
    assert len(logs) == 4, "Unexpected number of logs"
    assert_log_values(logs[0], 1)
    assert_log_values(logs[1], 2)
    assert_log_values(logs[2], 3)
    assert_log_values(logs[3], 100, previous_number=3)


def test_contract_logs_range_over_paging(contract_instance, owner, chain):
    # Create 1 log each in the first 3 blocks.
    for i in range(3):
        contract_instance.setNumber(i + 1, sender=owner)

    # 50 is way more than 3 but it shouldn't matter.
    logs = [log for log in contract_instance.NumberChange.range(100, block_page_size=50)]
    assert len(logs) == 3, "Unexpected number of logs"


def test_contract_logs_from_non_indexed_range(contract_instance, owner):
    contract_instance.setNumber(1, sender=owner)
    with pytest.raises(DecodingError):
        _ = [
            log for log in contract_instance.NumberChange.range(0, event_parameters={"prevNum": 1})
        ]


def test_poll_logs_stop_block_not_in_future(
    chain_at_block_5, vyper_contract_instance, eth_tester_provider
):
    bad_stop_block = chain_at_block_5.blocks.height

    with pytest.raises(ValueError) as err:
        _ = [x for x in vyper_contract_instance.NumberChange.poll_logs(stop_block=bad_stop_block)]

    assert str(err.value) == "'stop' argument must be in the future."


def test_poll_logs(vyper_contract_instance, eth_tester_provider, owner, poll_daemon):
    logs = Queue(maxsize=3)
    poller = vyper_contract_instance.NumberChange.poll_logs()

    with poll_daemon("logs", poller, logs.put, lambda: logs.full()):
        vyper_contract_instance.setNumber(1, sender=owner)
        vyper_contract_instance.setNumber(33, sender=owner)
        vyper_contract_instance.setNumber(7, sender=owner)
        eth_tester_provider.mine()  # Mine to fix race condition

    assert logs.full()
    log_0 = logs.get()
    log_1 = logs.get()
    log_2 = logs.get()
    assert log_0.newNum == 1
    assert log_1.newNum == 33
    assert log_2.newNum == 7
