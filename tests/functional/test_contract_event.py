import time
from queue import Queue
from typing import Optional

import pytest
from eth_pydantic_types import HexBytes
from eth_pydantic_types.hash import HashBytes20
from eth_utils import to_hex
from ethpm_types import ContractType

from ape.api.transactions import ReceiptAPI
from ape.exceptions import ProviderError
from ape.types.events import ContractLog
from ape.types.units import CurrencyValueComparable


@pytest.fixture
def assert_log_values(owner, chain):
    def _assert_log_values(log: ContractLog, number: int, previous_number: Optional[int] = None):
        assert isinstance(log.b, bytes)
        expected_previous_number = number - 1 if previous_number is None else previous_number
        assert log.prevNum == expected_previous_number, "Event param 'prevNum' has unexpected value"
        assert log.newNum == number, "Event param 'newNum' has unexpected value"
        assert log.newNum == f"{number} wei", "string comparison with number not working"
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

    assert event_type[0] == contract_instance.NumberChange(None, 0, None, 1)
    assert event_type[1] == contract_instance.NumberChange(None, 1, newNum=2)
    assert event_type[2] == contract_instance.NumberChange(newNum=3, prevNum=2)

    # Verify negative index access
    assert event_type[-3] == contract_instance.NumberChange(None, 0, None, 1)
    assert event_type[-2] == contract_instance.NumberChange(None, 1, newNum=2)
    assert event_type[-1] == contract_instance.NumberChange(newNum=3, prevNum=2)


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
    mocker, chain, eth_tester_provider, accounts, contract_instance, owner, assert_log_values
):
    get_logs_spy = mocker.spy(eth_tester_provider.tester.ethereum_tester, "get_logs")
    contract_instance.setAddress(accounts[1], sender=owner)
    height = chain.blocks.height
    logs = [
        log
        for log in contract_instance.AddressChange.range(
            height, height + 1, search_topics={"newAddress": accounts[1]}
        )
    ]

    # NOTE: This spy assertion tests against a bug where address queries were not
    # 0x-prefixed. However, this was still valid in EthTester and thus was not causing
    # test failures.
    height_arg = chain.blocks.height
    actual = get_logs_spy.call_args[-1]
    expected = {
        "address": [contract_instance.address],
        "from_block": height_arg,
        "to_block": height_arg,
        "topics": [
            "0x7ff7bacc6cd661809ed1ddce28d4ad2c5b37779b61b9e3235f8262be529101a9",
            "0x00000000000000000000000070997970c51812dc3a010c7d01b50e0d17dc79c8",
        ],
    }
    assert actual == expected
    assert logs == [contract_instance.AddressChange(newAddress=accounts[1])]


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
    assert logs[0] == contract_instance.NumberChange(newNum=1, prevNum=0)
    assert logs[1] == another_instance.NumberChange(newNum=1, prevNum=0)


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
    assert actual[0].block_number == actual[0].block.number == start_block + 1
    assert actual[1].block_number == actual[1].block.number == actual[0].block_number + 1
    assert actual[2].block_number == actual[2].block.number == actual[1].block_number + 1


def test_poll_logs_timeout(vyper_contract_instance, eth_tester_provider, owner, PollDaemon):
    new_block_timeout = 1
    poller = vyper_contract_instance.NumberChange.poll_logs(new_block_timeout=new_block_timeout)

    with pytest.raises(ProviderError) as err:
        with PollDaemon("logs", poller, lambda x: None, lambda: False):
            time.sleep(1.5)

    assert "Timed out waiting for next block" in str(err.value)


def test_contract_two_events_with_same_name(
    owner, chain, networks_connected_to_tester, shared_contracts_folder
):
    interface_path = shared_contracts_folder / "Interface.json"
    impl_path = shared_contracts_folder / "InterfaceImplementation.json"
    interface_text = interface_path.read_text(encoding="utf8")
    impl_text = impl_path.read_text(encoding="utf8")
    interface_contract_type = ContractType.model_validate_json(interface_text)
    impl_contract_type = ContractType.model_validate_json(impl_text)
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
    assert events == [contract_instance.NumberChange(newNum=1)]


def test_contract_decode_logs_falsy_check(owner, vyper_contract_instance):
    """
    Verifies a bug fix where false-y values differing were ignored.
    """

    tx = vyper_contract_instance.setNumber(1, sender=owner)
    with pytest.raises(AssertionError):
        assert tx.events == [vyper_contract_instance.NumberChange(newNum=0)]


def test_contract_log_container(owner, contract_instance):
    receipt = contract_instance.setNumber(1, sender=owner)
    events = receipt.events.filter(contract_instance.NumberChange, newNum=1)
    assert len(events) == 1


def test_filter_events_with_same_abi(
    owner, contract_with_call_depth, middle_contract, leaf_contract
):
    """
    Test shows that if we have a contract method emit multiple events with the
    same ABI, that each event only appears on the respective contract's
    filtering. This test verifies we filter by contract address as well as ABI.
    """

    tx = contract_with_call_depth.emitLogWithSameInterfaceFromMultipleContracts(sender=owner)

    assert contract_with_call_depth.OneOfMany(addr=owner.address) in tx.events
    assert middle_contract.OneOfMany(addr=contract_with_call_depth.address) in tx.events
    assert leaf_contract.OneOfMany(addr=contract_with_call_depth.address) in tx.events

    # Ensure each contract's event appears only once
    result_a = tx.events.filter(contract_with_call_depth.OneOfMany)
    assert result_a == [contract_with_call_depth.OneOfMany(addr=owner.address)]

    result_b = tx.events.filter(middle_contract.OneOfMany)
    assert result_b == [middle_contract.OneOfMany(addr=contract_with_call_depth.address)]

    result_c = tx.events.filter(leaf_contract.OneOfMany)
    assert result_c == [leaf_contract.OneOfMany(addr=contract_with_call_depth.address)]


def test_structs_in_events(contract_instance, owner, mystruct_c):
    tx = contract_instance.logStruct(sender=owner)
    expected_bytes = HexBytes(0x1234567890ABCDEF0123456789ABCDEF0123456789ABCDEF0123456789ABCDEF)
    expected = contract_instance.EventWithStruct(
        a_struct={"a": owner, "b": expected_bytes, "c": mystruct_c}
    )
    assert tx.events == [expected]


def test_address_arrays_in_events(contract_instance, owner):
    tx = contract_instance.logAddressArray(sender=owner)
    expected = contract_instance.EventWithAddressArray(
        some_id=1001, some_address=owner, participants=[owner], agents=[owner]
    )
    assert tx.events == [expected]


def test_uint_arrays_in_events(contract_instance, owner):
    tx = contract_instance.logUintArray(sender=owner)
    expected = contract_instance.EventWithUintArray(agents=[1])
    assert tx.events == [expected]


def test_info(solidity_contract_instance):
    event_type = solidity_contract_instance.NumberChange
    actual = event_type.info
    header = (
        "NumberChange(bytes32 b, uint256 prevNum, string dynData, "
        "uint256 indexed newNum, string indexed dynIndexed)"
    )
    spec = (
        "@details Emitted when number is changed. `newNum` is the new number "
        "from the call. Expected every time number changes."
    )
    expected = f"""
{header}
  {spec}
""".strip()
    assert actual == expected


def test_model_dump(solidity_contract_container, owner):
    # NOTE: deploying a new contract with a new number to lessen x-dist conflicts.
    contract = owner.deploy(solidity_contract_container, 29620000000003)

    # First, get an event (a normal way).
    number = int(10e18)
    tx = contract.setNumber(number, sender=owner)
    event = tx.events[0]

    # Next, invoke `.model_dump()` to get the serialized version.
    log = event.model_dump()
    actual = log["event_arguments"]
    assert actual["newNum"] == number

    # This next assertion is important because of this Pydantic bug:
    # https://github.com/pydantic/pydantic/issues/10152
    assert not isinstance(actual["newNum"], CurrencyValueComparable)


@pytest.mark.parametrize("mode", ("python", "json"))
def test_model_dump_hexbytes(mode):
    # NOTE: There was an issue when using HexBytes for Any.
    event_arguments = {"key": 123, "validators": [HexBytes(123)]}
    txn_hash = HashBytes20.__eth_pydantic_validate__(347374237412374174)
    event = ContractLog(
        block_number=123,
        block_hash="block-hash",
        event_arguments=event_arguments,
        event_name="MyEvent",
        log_index=0,
        transaction_hash=txn_hash,
    )
    actual = event.model_dump(mode=mode)
    expected_hash = txn_hash if mode == "python" else to_hex(txn_hash)
    assert actual["transaction_hash"] == expected_hash


def test_model_dump_json():
    # NOTE: There was an issue when using HexBytes for Any.
    event_arguments = {"key": 123, "validators": [HexBytes(123)]}
    event = ContractLog(
        block_number=123,
        block_hash="block-hash",
        event_arguments=event_arguments,
        event_name="MyEvent",
        log_index=0,
        transaction_hash=HashBytes20.__eth_pydantic_validate__(347374237412374174),
    )
    actual = event.model_dump_json()
    assert actual == (
        '{"block_hash":"block-hash","block_number":123,'
        '"contract_address":"0x0000000000000000000000000000000000000000",'
        '"event_arguments":{"key":123,"validators":["0x7b"]},"event_name":'
        '"MyEvent","log_index":0,'
        '"transaction_hash":"0x00000000000000000000000004d21f074916369e"}'
    )
