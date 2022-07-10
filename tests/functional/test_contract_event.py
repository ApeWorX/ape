import time
from pathlib import Path
from queue import Queue
from typing import Optional

import pytest
from ethpm_types import ContractType
from hexbytes import HexBytes

from ape.api import ReceiptAPI
from ape.exceptions import DecodingError
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


def test_poll_logs(vyper_contract_instance, eth_tester_provider, owner, PollDaemon):
    logs = Queue(maxsize=3)

    new_block_timeout = 5  # Set timeout to prevent never-ending tests.
    poller = vyper_contract_instance.NumberChange.poll_logs(new_block_timeout=new_block_timeout)

    with PollDaemon("logs", poller, logs.put, logs.full):
        vyper_contract_instance.setNumber(1, sender=owner)
        vyper_contract_instance.setNumber(33, sender=owner)
        vyper_contract_instance.setNumber(7, sender=owner)

        # Mine to ensure last log makes it before stopping polling.
        eth_tester_provider.mine()

    assert logs.full()
    assert all(logs.get().newNum == e for e in (1, 33, 7))


def test_poll_logs_timeout(vyper_contract_instance, eth_tester_provider, owner, PollDaemon, capsys):
    new_block_timeout = 1
    poller = vyper_contract_instance.NumberChange.poll_logs(new_block_timeout=new_block_timeout)

    with PollDaemon("logs", poller, lambda: None, False):
        time.sleep(1.5)

    _, err = capsys.readouterr()
    assert "ChainError: Timed out waiting for new block (time_waited=1." in str(err)


def test_contract_two_events_with_same_name(owner, networks_connected_to_tester):
    provider = networks_connected_to_tester
    base_path = Path(__file__).parent / "data" / "contracts" / "ethereum" / "local"
    interface_path = base_path / "Interface.json"
    impl_path = base_path / "InterfaceImplementation.json"
    interface_contract_type = ContractType.parse_raw(interface_path.read_text())
    impl_contract_type = ContractType.parse_raw(impl_path.read_text())
    event_name = "FooEvent"

    # Ensure test is setup correctly in case scenario-data changed on accident
    assert len([e for e in impl_contract_type.events if e.name == event_name]) == 2
    assert len([e for e in interface_contract_type.events if e.name == event_name]) == 1

    impl_container = provider.create_contract_container(impl_contract_type)
    impl_instance = owner.deploy(impl_container)

    with pytest.raises(AttributeError) as err:
        _ = impl_instance.FooEvent

    expected_err_prefix = f"Multiple events named '{event_name}'"
    assert expected_err_prefix in str(err.value)

    expected_sig_from_impl = "FooEvent(uint256 bar, uint256 baz)"
    expected_sig_from_interface = "FooEvent(uint256 bar)"
    event_from_impl_contract = impl_instance.get_event_by_signature(expected_sig_from_impl)
    assert event_from_impl_contract.abi.signature == expected_sig_from_impl
    event_from_interface = impl_instance.get_event_by_signature(expected_sig_from_interface)
    assert event_from_interface.abi.signature == expected_sig_from_interface
