import re

import pytest
from eth_utils import is_checksum_address, to_hex
from hexbytes import HexBytes

from ape import Contract
from ape.contracts import ContractInstance
from ape.exceptions import ChainError, ContractError, ContractLogicError
from ape.utils import ZERO_ADDRESS
from ape_ethereum.transactions import TransactionStatusEnum

from .conftest import TEST_ADDRESS

MATCH_TEST_CONTRACT = re.compile(r"<TestContract((Sol)|(Vy))")


def test_init_at_unknown_address(networks_connected_to_tester):
    _ = networks_connected_to_tester  # Need fixture or else get ProviderNotConnectedError
    with pytest.raises(
        ChainError, match=f"Failed to get contract type for address '{TEST_ADDRESS}'."
    ):
        Contract(TEST_ADDRESS)


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


def test_contract_calls(owner, contract_instance):
    contract_instance.setNumber(2, sender=owner)
    assert contract_instance.myNumber() == 2


def test_invoke_transaction(owner, contract_instance):
    # Test mutable method call with invoke_transaction
    receipt = contract_instance.invoke_transaction("setNumber", 3, sender=owner)
    assert contract_instance.myNumber() == 3
    assert not receipt.failed
    # Test view method can be called with invoke transaction and returns a receipt
    view_receipt = contract_instance.invoke_transaction("myNumber", sender=owner)
    assert not view_receipt.failed


def test_call_view_method(owner, contract_instance):
    contract_instance.setNumber(2, sender=owner)
    value = contract_instance.call_view_method("myNumber")
    assert value == 2
    # Test that a mutable method can be called and is treated as a call (a simulation)
    contract_instance.call_view_method("setNumber", 3, sender=owner)
    # myNumber should still equal 2 because the above line is call
    assert contract_instance.myNumber() == 2


def test_call_use_block_identifier(contract_instance, owner, chain):
    expected = 2
    contract_instance.setNumber(expected, sender=owner)
    block_id = chain.blocks.height  # int
    contract_instance.setNumber(3, sender=owner)  # latest
    actual = contract_instance.myNumber(block_identifier=block_id)
    assert actual == expected

    # Ensure works with hex
    block_id = to_hex(block_id)
    actual = contract_instance.myNumber(block_identifier=block_id)
    assert actual == expected

    # Ensure works keywords like "latest"
    actual = contract_instance.myNumber(block_identifier="latest")
    assert actual == 3


def test_revert(sender, contract_instance):
    # 'sender' is not the owner so it will revert (with a message)
    with pytest.raises(ContractLogicError, match="!authorized"):
        contract_instance.setNumber(5, sender=sender)


def test_revert_no_message(owner, contract_instance):
    # The Contract raises empty revert when setting number to 5.
    expected = "Transaction failed."  # Default message
    with pytest.raises(ContractLogicError, match=expected):
        contract_instance.setNumber(5, sender=owner)


@pytest.mark.parametrize("gas", ("200000", 200000, "max", "auto", "0x235426"))
def test_revert_specify_gas(sender, contract_instance, gas):
    with pytest.raises(ContractLogicError, match="!authorized"):
        contract_instance.setNumber(5, sender=sender, gas=gas)


def test_call_using_block_identifier(
    vyper_contract_instance, owner, chain, networks_connected_to_tester
):
    contract = vyper_contract_instance
    contract.setNumber(1, sender=owner)
    height = chain.blocks.height
    contract.setNumber(33, sender=owner)
    actual = contract.myNumber(block_identifier=height)
    assert actual == 1


def test_repr(contract_instance):
    assert re.match(
        rf"<TestContract((Sol)|(Vy)) {contract_instance.address}>", repr(contract_instance)
    )
    assert repr(contract_instance.setNumber) == "setNumber(uint256 num)"
    assert repr(contract_instance.myNumber) == "myNumber() -> uint256"
    assert (
        repr(contract_instance.NumberChange) == "NumberChange(bytes32 b, uint256 prevNum, "
        "string dynData, uint256 indexed newNum, string indexed dynIndexed)"
    )


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
    assert contract_instance.getEmptyArray() == []
    assert contract_instance.getSingleItemArray() == [1]
    assert contract_instance.getFilledArray() == [1, 2, 3]


def test_address_arrays(contract_instance, sender):
    actual = contract_instance.getAddressArray()
    assert actual == [sender, sender]
    assert is_checksum_address(actual[0])
    assert is_checksum_address(actual[1])


def test_contract_instance_as_address_input(contract_instance, sender):
    contract_instance.setAddress(contract_instance, sender=sender)
    assert contract_instance.theAddress() == contract_instance


def test_account_as_address_input(contract_instance, sender):
    contract_instance.setAddress(sender, sender=sender)
    assert contract_instance.theAddress() == sender


def test_int_as_address_input(contract_instance, sender):
    contract_instance.setAddress(int(sender.address, 16), sender=sender)
    assert contract_instance.theAddress() == sender


def test_vyper_struct_arrays(vyper_contract_instance, sender):
    # NOTE: Vyper struct arrays <=0.3.3 don't include struct info
    actual_dynamic = vyper_contract_instance.getDynamicStructArray()
    assert len(actual_dynamic) == 2
    assert actual_dynamic[0][0][0] == sender
    assert is_checksum_address(actual_dynamic[0][0][0])
    assert actual_dynamic[0][1] == 1
    assert actual_dynamic[1][0][0] == sender
    assert is_checksum_address(actual_dynamic[1][0][0])
    assert actual_dynamic[1][1] == 2

    actual_static = vyper_contract_instance.getStaticStructArray()
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
        actual_dynamic = solidity_contract_instance.getDynamicStructArray()
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
        actual_dynamic = solidity_contract_instance.getStaticStructArray()
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


def test_get_array_with_bigger_size(contract_instance):
    # Tests against bug where if array had size > 9, it would fail to parse.
    # Method set to return an array of size 20
    actual = contract_instance.getArrayWithBiggerSize()
    assert actual == [0] * 20


def test_get_tuple_of_arrays(contract_instance):
    actual = contract_instance.getTupleOfArrays()
    assert actual == ([0] * 20, [0] * 20)


def test_vyper_named_tuple(vyper_contract_instance):
    actual = vyper_contract_instance.getMultipleValues()
    assert actual == (123, 321)


def test_get_unnamed_tuple(contract_instance):
    actual = contract_instance.getUnnamedTuple()
    assert actual == (0, 0)


def test_get_tuple_of_address_array(contract_instance):
    actual = contract_instance.getTupleOfAddressArray()
    assert len(actual) == 2
    assert len(actual[0]) == 20
    assert is_checksum_address(actual[0][0])
    assert all(x == ZERO_ADDRESS for x in actual[0][1:])
    assert actual[1] == [0] * 20


def test_get_nested_array_fixed_fixed(contract_instance):
    actual = contract_instance.getNestedArrayFixedFixed()
    assert actual == [[1, 2], [3, 4], [5, 6]]


def test_get_nested_array_dynamic_fixed(contract_instance, owner):
    actual = contract_instance.getNestedArrayDynamicFixed()
    assert actual == [[1, 2], [3, 4], [5, 6]]


def test_get_nested_array_fixed_dynamic(contract_instance, owner):
    actual = contract_instance.getNestedArrayFixedDynamic()
    assert actual == [[0], [0, 1], [0, 1, 2]]


def test_get_nested_array_mixed_dynamic(contract_instance, owner):
    actual = contract_instance.getNestedArrayMixedDynamic()
    assert len(actual) == 5
    assert len(actual[0]) == 1
    assert len(actual[1]) == 2
    assert actual[0][0] == [[0], [0, 1], [0, 1, 2]]
    assert actual[1][0] == [[0], [0, 1], [0, 1, 2]]
    assert actual[1][1] == [[0], [0, 1], [0, 1, 2]]
    assert actual[2] == actual[3] == actual[4] == []


def test_get_nested_address_array(contract_instance, sender):
    actual = contract_instance.getNestedAddressArray()
    assert len(actual) == 2
    assert len(actual[0]) == 3
    assert len(actual[1]) == 3
    assert actual[0] == [sender, sender, sender]
    assert actual[1] == [ZERO_ADDRESS, ZERO_ADDRESS, ZERO_ADDRESS]


def test_call_transaction(contract_instance, owner, chain):
    # Transaction never submitted because using `call`.
    init_block = chain.blocks[-1]
    contract_instance.setNumber.call(1, sender=owner)

    # No mining happens because its a call
    assert init_block == chain.blocks[-1]


def test_estimate_gas_cost_txn(vyper_contract_instance, eth_tester_provider, owner):
    gas_cost = vyper_contract_instance.setNumber.estimate_gas_cost(10, sender=owner)
    assert gas_cost > 0


def test_estimate_gas_cost_call(vyper_contract_instance, eth_tester_provider, owner):
    gas_cost = vyper_contract_instance.myNumber.estimate_gas_cost(sender=owner)
    assert gas_cost > 0


def test_estimate_gas_cost_account_as_input(vyper_contract_instance, eth_tester_provider, owner):
    gas_cost = vyper_contract_instance.setAddress.estimate_gas_cost(owner, sender=owner)
    assert gas_cost > 0


def test_estimate_gas_cost_call_account_as_input(contract_instance, eth_tester_provider, owner):
    assert contract_instance.balances.estimate_gas_cost(owner) > 0


def test_call_transact(vyper_contract_instance, owner):
    receipt = vyper_contract_instance.myNumber.transact(sender=owner)
    assert receipt.sender == owner
    assert receipt.status == TransactionStatusEnum.NO_ERROR


def test_receipt(contract_instance, owner):
    receipt = contract_instance.receipt
    assert receipt.txn_hash == contract_instance.txn_hash
    assert receipt.contract_address == contract_instance.address
    assert receipt.sender == owner


def test_from_receipt_when_receipt_not_deploy(contract_instance, owner):
    receipt = contract_instance.setNumber(555, sender=owner)
    expected_err = (
        "Receipt missing 'contract_address' field. "
        "Was this from a deploy transaction (e.g. `project.MyContract.deploy()`)?"
    )
    with pytest.raises(ContractError, match=expected_err):
        ContractInstance.from_receipt(receipt, contract_instance.contract_type)


def test_transact_specify_auto_gas(vyper_contract_instance, owner):
    """
    Tests that we can specify "auto" gas even though "max" is the default for
    local networks.
    """
    receipt = vyper_contract_instance.setNumber(111, sender=owner, gas="auto")
    assert not receipt.failed


def test_transact_specify_max_gas(vyper_contract_instance, owner):
    receipt = vyper_contract_instance.setNumber(222, sender=owner, gas="max")
    assert not receipt.failed


def test_dir(vyper_contract_instance):
    actual = dir(vyper_contract_instance)
    expected = [
        # From base class
        "address",
        "balance",
        "code",
        "contract_type",
        "codesize",
        "nonce",
        "is_contract",
        "provider",
        "receipt",
        "txn_hash",
        *vyper_contract_instance._events_,
        *vyper_contract_instance._mutable_methods_,
        *vyper_contract_instance._view_methods_,
    ]
    assert sorted(actual) == sorted(expected)
