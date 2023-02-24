import time
from queue import Queue
from typing import Optional

import pytest
from eth_utils import to_hex
from ethpm_types import ContractType
from hexbytes import HexBytes

from ape.api import ReceiptAPI
from ape.exceptions import ChainError
from ape.types import ContractLog


@pytest.fixture
def assert_log_values(owner, chain):
    def _assert_log_values(log: ContractLog, number: int, previous_number: Optional[int] = None):
        assert isinstance(log.b, HexBytes)
        expected_previous_number = number - 1 if previous_number is None else previous_number
        assert log.prevNum == expected_previous_number, "Event param 'prevNum' has unexpected value"
        assert log.newNum == number, "Event param 'newNum' has unexpected value"
        assert log.dynData == "Dynamic"
        assert log.dynIndexed == HexBytes(
            "0x9f3d45ac20ccf04b45028b8080bb191eab93e29f7898ed43acf480dd80bba94d"
        )

    return _assert_log_values


def test_contract_logs_from_receipts(owner, contract_instance, assert_log_values):
    event_type = contract_instance.NumberChange

    # Invoke a transaction 3 times that generates 3 logs.
    receipt_0 = contract_instance.setNumber(1, sender=owner)
    receipt_1 = contract_instance.setNumber(2, sender=owner)
    receipt_2 = contract_instance.setNumber(3, sender=owner)

    def assert_receipt_logs(receipt: ReceiptAPI, num: int):
        logs = event_type.from_receipt(receipt)
        assert len(logs) == 1
        assert_log_values(logs[0], num)

        # Also verify can we logs the other way
        logs = receipt.decode_logs(event_type)
        assert len(logs) == 1
        assert_log_values(logs[0], num)

    assert_receipt_logs(receipt_0, 1)
    assert_receipt_logs(receipt_1, 2)
    assert_receipt_logs(receipt_2, 3)


def test_contract_logs_from_event_type(contract_instance, owner, assert_log_values):
    event_type = contract_instance.NumberChange
    start_num = 6
    size = 20
    num_range = range(start_num, start_num + size)

    # Generate 20 logs
    for i in num_range:
        contract_instance.setNumber(i, sender=owner)

    # Collect 20 logs
    logs = [log for log in event_type]

    assert len(logs) == size, "Unexpected number of logs"
    for num, log in zip(num_range, logs):
        if num == start_num:
            assert_log_values(log, num, previous_number=0)
        else:
            assert_log_values(log, num)


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


def test_contract_logs_range(chain, contract_instance, owner, assert_log_values):
    contract_instance.setNumber(1, sender=owner)
    start = chain.blocks.height
    logs = [
        log
        for log in contract_instance.NumberChange.range(
            start, start + 100, search_topics={"newNum": 1}
        )
    ]
    assert len(logs) == 1, "Unexpected number of logs"
    assert_log_values(logs[0], 1)


def test_contract_logs_range_by_address(
    mocker, chain, eth_tester_provider, test_accounts, contract_instance, owner, assert_log_values
):
    get_logs_spy = mocker.spy(eth_tester_provider.web3.eth, "get_logs")
    contract_instance.setAddress(test_accounts[1], sender=owner)
    height = chain.blocks.height
    logs = [
        log
        for log in contract_instance.AddressChange.range(
            height, height + 1, search_topics={"newAddress": test_accounts[1]}
        )
    ]

    # NOTE: This spy assertion tests against a bug where address queries were not
    # 0x-prefixed. However, this was still valid in EthTester and thus was not causing
    # test failures.
    height_arg = to_hex(chain.blocks.height)
    get_logs_spy.assert_called_once_with(
        {
            "address": [contract_instance.address],
            "fromBlock": height_arg,
            "toBlock": height_arg,
            "topics": [
                "0x7ff7bacc6cd661809ed1ddce28d4ad2c5b37779b61b9e3235f8262be529101a9",
                "0x000000000000000000000000c89d42189f0450c2b2c3c61f58ec5d628176a1e7",
            ],
        }
    )
    assert len(logs) == 1
    assert logs[0].newAddress == test_accounts[1]


def test_contracts_log_multiple_addresses(
    chain, contract_instance, contract_container, owner, assert_log_values
):
    another_instance = contract_container.deploy(0, sender=owner)
    start_block = chain.blocks.height
    contract_instance.setNumber(1, sender=owner)
    another_instance.setNumber(1, sender=owner)

    logs = [
        log
        for log in contract_instance.NumberChange.range(
            start_block,
            start_block + 100,
            search_topics={"newNum": 1},
            extra_addresses=[another_instance.address],
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

    stop = start_block + 30  # Stop can be bigger than height, it doesn't not matter
    logs = [log for log in contract_instance.NumberChange.range(start_block, stop=stop)]
    assert len(logs) == 3, "Unexpected number of logs"


def test_contract_logs_range_only_stop(contract_instance, owner, chain):
    # Create 1 event
    start = chain.blocks.height
    contract_instance.setNumber(1, sender=owner)
    contract_instance.setNumber(2, sender=owner)
    contract_instance.setNumber(3, sender=owner)

    stop = start + 100  # Stop can be bigger than height, it doesn't not matter
    logs = [log for log in contract_instance.NumberChange.range(stop)]
    assert len(logs) >= 3, "Unexpected number of logs"


def test_poll_logs_stop_block_not_in_future(
    chain_that_mined_5, vyper_contract_instance, eth_tester_provider
):
    bad_stop_block = chain_that_mined_5.blocks.height

    with pytest.raises(ValueError, match="'stop' argument must be in the future."):
        _ = [x for x in vyper_contract_instance.NumberChange.poll_logs(stop_block=bad_stop_block)]


def test_poll_logs(chain, vyper_contract_instance, eth_tester_provider, owner, PollDaemon):
    size = 3
    logs: Queue = Queue(maxsize=size)
    poller = vyper_contract_instance.NumberChange.poll_logs(start_block=0)
    start_block = chain.blocks.height

    with PollDaemon("logs", poller, logs.put, logs.full):
        # Sleep first to ensure listening before emitting logs.
        time.sleep(1)

        vyper_contract_instance.setNumber(1, sender=owner)  # block s+1
        vyper_contract_instance.setNumber(33, sender=owner)  # block s+2
        vyper_contract_instance.setNumber(7, sender=owner)  # block s+3

    actual = [logs.get() for _ in range(size)]
    assert all(a.newNum == e for a, e in zip(actual, (1, 33, 7)))
    assert actual[0].block_number == start_block + 1
    assert actual[1].block_number == actual[0].block_number + 1
    assert actual[2].block_number == actual[1].block_number + 1


def test_poll_logs_timeout(vyper_contract_instance, eth_tester_provider, owner, PollDaemon):
    new_block_timeout = 1
    poller = vyper_contract_instance.NumberChange.poll_logs(new_block_timeout=new_block_timeout)

    with pytest.raises(ChainError) as err:
        with PollDaemon("logs", poller, lambda x: None, lambda: False):
            time.sleep(1.5)

    assert "Timed out waiting for new block (time_waited=1" in str(err.value)


def test_contract_two_events_with_same_name(
    owner, chain, networks_connected_to_tester, contracts_folder
):
    interface_path = contracts_folder / "Interface.json"
    impl_path = contracts_folder / "InterfaceImplementation.json"
    interface_contract_type = ContractType.parse_raw(interface_path.read_text())
    impl_contract_type = ContractType.parse_raw(impl_path.read_text())
    event_name = "FooEvent"

    # Ensure test is setup correctly in case scenario-data changed on accident
    assert len([e for e in impl_contract_type.events if e.name == event_name]) == 2
    assert len([e for e in interface_contract_type.events if e.name == event_name]) == 1

    impl_container = chain.contracts.get_container(impl_contract_type)
    impl_instance = owner.deploy(impl_container)

    expected_err = (
        f"Multiple events named '{event_name}' in '{impl_contract_type.name}'.\n"
        f"Use 'get_event_by_signature' look-up."
    )
    with pytest.raises(AttributeError, match=expected_err):
        _ = impl_instance.FooEvent

    expected_sig_from_impl = "FooEvent(uint256 bar, uint256 baz)"
    expected_sig_from_interface = "FooEvent(uint256 bar)"
    event_from_impl_contract = impl_instance.get_event_by_signature(expected_sig_from_impl)
    assert event_from_impl_contract.abi.signature == expected_sig_from_impl
    event_from_interface = impl_instance.get_event_by_signature(expected_sig_from_interface)
    assert event_from_interface.abi.signature == expected_sig_from_interface


def test_contract_decode_logs_no_abi(owner, contract_instance):
    receipt = contract_instance.setNumber(1, sender=owner)
    events = list(receipt.decode_logs())  # no abi
    assert len(events) == 1
    assert events[0].event_name == "NumberChange"
    assert events[0].newNum == 1
    assert events[0].transaction_index == 0


def test_contract_log_container(owner, contract_instance):
    receipt = contract_instance.setNumber(1, sender=owner)
    events = receipt.events.filter(contract_instance.NumberChange, newNum=1)
    assert len(events) == 1
