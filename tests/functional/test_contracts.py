import re
from typing import Optional

import pytest
from eth_utils import is_checksum_address
from hexbytes import HexBytes

from ape import Contract
from ape.api import Address, ReceiptAPI
from ape.exceptions import DecodingError
from ape.types import ContractLog

SOLIDITY_CONTRACT_ADDRESS = "0xBcF7FFFD8B256Ec51a36782a52D0c34f6474D951"
VYPER_CONTRACT_ADDRESS = "0x274b028b03A250cA03644E6c578D81f019eE1323"
MATCH_TEST_CONTRACT = re.compile(r"<TestContract((Sol)|(Vy))")


@pytest.fixture
def assert_log_values(owner, chain):
    def _assert_log_values(log: ContractLog, number: int, previous_number: Optional[int] = None):
        assert log.person == owner
        assert is_checksum_address(log.person)
        assert isinstance(log.b, HexBytes)

        expected_previous_number = number - 1 if previous_number is None else previous_number
        assert log.prevNum == expected_previous_number, "Event param 'prevNum' has unexpected value"
        assert log.newNum == number, "Event param 'newNum' has unexpected value"

    return _assert_log_values


def test_init_at_unknown_address():
    contract = Contract(SOLIDITY_CONTRACT_ADDRESS)
    assert type(contract) == Address
    assert contract.address == SOLIDITY_CONTRACT_ADDRESS


def test_init_specify_contract_type(
    solidity_contract_instance, vyper_contract_type, owner, networks_connected_to_tester
):
    # Vyper contract type is very close to solidity's.
    # This test purposely uses the other just to show we are able to specify it externally.
    contract = Contract(solidity_contract_instance.address, contract_type=vyper_contract_type)
    assert contract.address == solidity_contract_instance.address
    assert contract.contract_type == vyper_contract_type
    assert contract.setNumber(2, sender=owner)
    assert contract.myNumber() == 2


def test_deploy(
    sender, contract_container, networks_connected_to_tester, project, chain, clean_contracts_cache
):
    contract = contract_container.deploy(sender=sender, something_else="IGNORED")
    assert contract.address in (SOLIDITY_CONTRACT_ADDRESS, VYPER_CONTRACT_ADDRESS)

    # Verify can reload same contract from cache
    contract_from_cache = Contract(contract.address)
    assert contract_from_cache.contract_type == contract.contract_type
    assert contract_from_cache.address == contract.address

    # Clean up for next test
    del chain.contracts._local_contracts[contract_from_cache.address]


def test_repr(contract_instance):
    assert re.match(
        rf"<TestContract((Sol)|(Vy)) {contract_instance.address}>", repr(contract_instance)
    )
    assert repr(contract_instance.setNumber) == "setNumber(uint256 num)"
    assert repr(contract_instance.myNumber) == "myNumber() -> uint256"
    assert (
        repr(contract_instance.NumberChange)
        == "NumberChange(address person, bytes32 b, uint256 prevNum, uint256 indexed newNum)"
    )


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


def test_structs(contract_instance, sender, chain):
    actual = contract_instance.getStruct()
    actual_sender, actual_prev_block = actual

    # Expected: a == msg.sender
    assert actual.a == actual["a"] == actual[0] == actual_sender == sender
    assert is_checksum_address(actual.a)

    # Expected: b == block.prevhash.
    assert actual.b == actual["b"] == actual[1] == actual_prev_block == chain.blocks[-2].hash
    assert type(actual.b) == HexBytes


def test_nested_structs(contract_instance, sender, chain):
    actual_1 = contract_instance.getNestedStruct1()
    actual_2 = contract_instance.getNestedStruct2()
    actual_sender_1, actual_prev_block_1 = actual_1.t
    actual_sender_2, actual_prev_block_2 = actual_2.t

    # Expected: t.a == msg.sender
    assert actual_1.t.a == actual_1.t["a"] == actual_1.t[0] == actual_sender_1 == sender
    assert is_checksum_address(actual_1.t.a)
    assert is_checksum_address(actual_sender_1)
    assert actual_1.foo == 1
    assert actual_2.t.a == actual_2.t["a"] == actual_2.t[0] == actual_sender_2 == sender
    assert is_checksum_address(actual_2.t.a)
    assert is_checksum_address(actual_sender_2)
    assert actual_2.foo == 2

    # Expected: t.b == block.prevhash.
    assert (
        actual_1.t.b
        == actual_1.t["b"]
        == actual_1.t[1]
        == actual_prev_block_1
        == chain.blocks[-2].hash
    )
    assert type(actual_1.t.b) == HexBytes
    assert (
        actual_2.t.b
        == actual_2.t["b"]
        == actual_2.t[1]
        == actual_prev_block_2
        == chain.blocks[-2].hash
    )
    assert type(actual_2.t.b) == HexBytes


def test_nested_structs_in_tuples(contract_instance, sender, chain):
    result_1 = contract_instance.getNestedStructWithTuple1()
    struct_1 = result_1[0]
    assert result_1[1] == 1
    assert struct_1.foo == 1
    assert struct_1.t.a == sender
    assert is_checksum_address(struct_1.t.a)

    result_2 = contract_instance.getNestedStructWithTuple2()
    struct_2 = result_2[1]
    assert result_2[0] == 2
    assert struct_2.foo == 2
    assert struct_2.t.a == sender
    assert is_checksum_address(struct_2.t.a)


def test_vyper_structs_with_array(vyper_contract_instance, sender):
    # NOTE: Vyper struct arrays <=0.3.3 don't include struct info
    actual = vyper_contract_instance.getStructWithArray()
    assert actual.foo == 1
    assert actual.bar == 2
    assert len(actual.arr) == 2


def test_solidity_structs_with_array(solidity_contract_instance, sender):
    actual = solidity_contract_instance.getStructWithArray()
    assert actual.foo == 1
    assert actual.bar == 2
    assert len(actual.arr) == 2, "Unexpected array length"
    assert actual.arr[0].a == sender
    assert is_checksum_address(actual.arr[0].a)


def test_arrays(contract_instance, sender):
    assert contract_instance.getEmptyList() == []
    assert contract_instance.getSingleItemList() == [1]
    assert contract_instance.getFilledList() == [1, 2, 3]


def test_address_arrays(contract_instance, sender):
    actual = contract_instance.getAddressList()
    assert actual == [sender, sender]
    assert is_checksum_address(actual[0])
    assert is_checksum_address(actual[1])


def test_vyper_struct_arrays(vyper_contract_instance, sender):
    # NOTE: Vyper struct arrays <=0.3.3 don't include struct info
    actual_dynamic = vyper_contract_instance.getDynamicStructList()
    assert len(actual_dynamic) == 2
    assert actual_dynamic[0][0][0] == sender
    assert is_checksum_address(actual_dynamic[0][0][0])
    assert actual_dynamic[0][1] == 1
    assert actual_dynamic[1][0][0] == sender
    assert is_checksum_address(actual_dynamic[1][0][0])
    assert actual_dynamic[1][1] == 2

    actual_static = vyper_contract_instance.getStaticStructList()
    assert len(actual_static) == 2
    assert actual_static[0][0] == 1
    assert actual_static[0][1][0] == sender
    assert is_checksum_address(actual_static[0][1][0])
    assert actual_static[1][0] == 2
    assert actual_static[1][1][0] == sender
    assert is_checksum_address(actual_static[1][1][0])


def test_solidity_dynamic_struct_arrays(solidity_contract_instance, sender):
    # Run test twice to make sure we can call method more than 1 time and have
    # the same result.
    for _ in range(2):
        actual_dynamic = solidity_contract_instance.getDynamicStructList()
        assert len(actual_dynamic) == 2
        assert actual_dynamic[0].foo == 1
        assert actual_dynamic[0].t.a == sender
        assert is_checksum_address(actual_dynamic[0].t.a)

        assert actual_dynamic[1].foo == 2
        assert actual_dynamic[1].t.a == sender
        assert is_checksum_address(actual_dynamic[1].t.a)


def test_solidity_static_struct_arrays(solidity_contract_instance, sender):
    # Run test twice to make sure we can call method more than 1 time and have
    # the same result.
    for _ in range(2):
        actual_dynamic = solidity_contract_instance.getStaticStructList()
        assert len(actual_dynamic) == 2
        assert actual_dynamic[0].foo == 1
        assert actual_dynamic[0].t.a == sender
        assert is_checksum_address(actual_dynamic[0].t.a)

        assert actual_dynamic[1].foo == 2
        assert actual_dynamic[1].t.a == sender
        assert is_checksum_address(actual_dynamic[1].t.a)


def test_solidity_named_tuple(solidity_contract_instance):
    actual = solidity_contract_instance.getNamedSingleItem()
    assert actual == 123

    actual = solidity_contract_instance.getTupleAllNamed()
    assert actual == (123, 321)
    assert actual.foo == 123
    assert actual.bar == 321

    actual = solidity_contract_instance.getPartiallyNamedTuple()
    assert actual == (123, 321)


def test_vyper_named_tuple(vyper_contract_instance):
    actual = vyper_contract_instance.getMultipleValues()
    assert actual == (123, 321)


def test_call_transaction(contract_instance, owner, chain):
    # Transaction never submitted because using `call`.
    init_block = chain.blocks[-1]
    contract_instance.setNumber.call(1, sender=owner)

    # No mining happens because its a call
    assert init_block == chain.blocks[-1]
