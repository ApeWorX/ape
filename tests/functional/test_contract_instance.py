import re
from typing import List, Tuple

import pytest
from eth_utils import is_checksum_address, to_hex
from ethpm_types import ContractType, HexBytes
from pydantic import BaseModel

from ape import Contract
from ape.api import TransactionAPI
from ape.contracts import ContractInstance
from ape.exceptions import (
    APINotImplementedError,
    ArgumentsLengthError,
    ChainError,
    ContractError,
    ContractLogicError,
    CustomError,
)
from ape.types import AddressType
from ape_ethereum.transactions import TransactionStatusEnum

MATCH_TEST_CONTRACT = re.compile(r"<TestContract((Sol)|(Vy))")


@pytest.fixture
def data_object(owner):
    class DataObject(BaseModel):
        a: AddressType = owner.address
        b: HexBytes = HexBytes(123)
        c: str = "GETS IGNORED"

    return DataObject()


def test_init_at_unknown_address(networks_connected_to_tester, address):
    _ = networks_connected_to_tester  # Need fixture or else get ProviderNotConnectedError
    with pytest.raises(ChainError, match=f"Failed to get contract type for address '{address}'."):
        Contract(address)


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


def test_eq(vyper_contract_instance, chain):
    other = chain.contracts.instance_at(vyper_contract_instance.address)
    assert other == vyper_contract_instance


def test_contract_transactions(owner, contract_instance):
    contract_instance.setNumber(2, sender=owner)
    assert contract_instance.myNumber() == 2


def test_wrong_number_of_arguments(owner, contract_instance):
    if "sol" in contract_instance.contract_type.source_id.lower():
        second = r"\n\t.*setNumber\(uint256 num, address _address\).*"
    else:
        second = ""

    expected = (
        r"The number of the given arguments \(4\) do not match what is defined in the ABI:\n"
        r"\n\t.*setNumber\(uint256 num\).*"
        f"{second}"
    )
    with pytest.raises(ArgumentsLengthError, match=expected):
        contract_instance.setNumber(2, 3, 5, 6, sender=owner)


@pytest.mark.parametrize("type_param", (0, "0", HexBytes(0)))
def test_static_fee_txn(owner, vyper_contract_instance, type_param):
    receipt = vyper_contract_instance.setNumber(4, sender=owner, type=type_param)
    assert vyper_contract_instance.myNumber() == 4
    assert not receipt.failed
    assert receipt.type == 0


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
    with pytest.raises(ContractLogicError, match="!authorized") as err:
        contract_instance.setNumber(5, sender=sender)

    assert err.value.txn is not None


def test_revert_no_message(owner, contract_instance):
    # The Contract raises empty revert when setting number to 5.
    expected = "Transaction failed."  # Default message
    with pytest.raises(ContractLogicError, match=expected) as err:
        contract_instance.setNumber(5, sender=owner)

    assert err.value.txn is not None


@pytest.mark.parametrize("gas", ("200000", 200000, "max", "auto", "0x235426"))
def test_revert_specify_gas(sender, contract_instance, gas):
    with pytest.raises(ContractLogicError, match="!authorized") as err:
        contract_instance.setNumber(5, sender=sender, gas=gas)

    assert err.value.txn is not None


def test_revert_no_message_specify_gas(owner, contract_instance):
    expected = "Transaction failed."  # Default message
    with pytest.raises(ContractLogicError, match=expected) as err:
        contract_instance.setNumber(5, sender=owner, gas=200000)

    assert err.value.txn is not None


def test_revert_static_fee_type(sender, contract_instance):
    with pytest.raises(ContractLogicError, match="!authorized") as err:
        contract_instance.setNumber(5, sender=sender, type=0)

    assert err.value.txn is not None


def test_revert_custom_exception(not_owner, error_contract):
    with pytest.raises(ContractLogicError) as err_info:
        error_contract.withdraw(sender=not_owner)

    custom_err = err_info.value
    addr = not_owner.address
    expected_message = f"addr={addr}, counter=123"
    assert custom_err.txn is not None
    assert custom_err.message == expected_message
    assert custom_err.revert_message == expected_message
    assert custom_err.inputs == {"addr": addr, "counter": 123}  # type: ignore


def test_call_using_block_identifier(
    vyper_contract_instance, owner, chain, networks_connected_to_tester
):
    contract = vyper_contract_instance
    contract.setNumber(1, sender=owner)
    height = chain.blocks.height
    contract.setNumber(33, sender=owner)
    actual = contract.myNumber(block_identifier=height)
    assert actual == 1


def test_repr(vyper_contract_instance):
    assert re.match(
        rf"<TestContract((Sol)|(Vy)) {vyper_contract_instance.address}>",
        repr(vyper_contract_instance),
    )
    assert (
        repr(vyper_contract_instance.setNumber)
        == "<TestContractVy 0xF7F78379391C5dF2Db5B66616d18fF92edB82022>.setNumber"
    )
    assert str(vyper_contract_instance.setNumber) == "setNumber(uint256 num)"
    assert (
        repr(vyper_contract_instance.myNumber)
        == "<TestContractVy 0xF7F78379391C5dF2Db5B66616d18fF92edB82022>.myNumber"
    )
    assert str(vyper_contract_instance.myNumber) == "myNumber() -> uint256"
    assert (
        repr(vyper_contract_instance.NumberChange) == "NumberChange(bytes32 b, uint256 prevNum, "
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


def test_get_empty_dyn_array_of_structs(contract_instance):
    actual = contract_instance.getEmptyDynArrayOfStructs()
    expected: List = []
    assert actual == expected


def test_get_empty_tuple_of_dyn_array_structs(contract_instance):
    actual = contract_instance.getEmptyTupleOfDynArrayStructs()
    expected: Tuple[List, List] = ([], [])
    assert actual == expected


def test_get_empty_tuple_of_array_of_structs_and_dyn_array_of_structs(
    contract_instance, zero_address
):
    actual = contract_instance.getEmptyTupleOfArrayOfStructsAndDynArrayOfStructs()
    expected_fixed_array = (
        zero_address,
        HexBytes("0x0000000000000000000000000000000000000000000000000000000000000000"),
    )
    assert actual[0] == [expected_fixed_array, expected_fixed_array, expected_fixed_array]
    assert actual[1] == []


def test_get_tuple_of_int_and_struct_array(contract_instance):
    actual_int, actual_struct_array = contract_instance.getTupleOfIntAndStructArray()
    assert actual_int == 0
    assert len(actual_struct_array) == 5
    assert len(actual_struct_array[0]) == 6


def test_get_empty_tuple_of_int_and_dyn_array(contract_instance):
    actual = contract_instance.getEmptyTupleOfIntAndDynArray()
    expected: Tuple[List, List] = ([], [])
    assert actual == expected


def test_vyper_structs_with_array(vyper_contract_instance):
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


def test_arrays(contract_instance):
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
        assert len(actual_dynamic) == 3
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


def test_get_tuple_of_address_array(contract_instance, zero_address):
    actual = contract_instance.getTupleOfAddressArray()
    assert len(actual) == 2
    assert len(actual[0]) == 20
    assert is_checksum_address(actual[0][0])
    assert all(x == zero_address for x in actual[0][1:])
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


def test_get_nested_address_array(contract_instance, sender, zero_address):
    actual = contract_instance.getNestedAddressArray()
    assert len(actual) == 2
    assert len(actual[0]) == 3
    assert len(actual[1]) == 3
    assert actual[0] == [sender, sender, sender]
    assert actual[1] == [zero_address, zero_address, zero_address]


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


def test_receipt_when_needs_brute_force(vyper_contract_instance, owner):
    # Force it to use the brute-force approach.
    vyper_contract_instance._cached_receipt = None
    vyper_contract_instance.txn_hash = None

    actual = vyper_contract_instance.receipt.contract_address
    expected = vyper_contract_instance.address
    assert actual == expected


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


@pytest.mark.parametrize("gas_kwarg", ("gas", "gas_limit"))
def test_transaction_specific_gas(vyper_contract_instance, owner, gas_kwarg):
    gas = 400000
    kwargs = {"sender": owner, gas_kwarg: gas}
    receipt = vyper_contract_instance.setNumber(222, **kwargs)
    assert not receipt.failed
    assert receipt.gas_limit == gas


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
        "decode_input",
        "get_event_by_signature",
        "invoke_transaction",
        "call_view_method",
        *vyper_contract_instance._events_,
        *vyper_contract_instance._mutable_methods_,
        *vyper_contract_instance._view_methods_,
    ]
    assert sorted(actual) == sorted(expected)


def test_encode_call_input(contract_instance, calldata):
    method = contract_instance.setNumber.call
    actual = method.encode_input(222)
    expected = calldata
    assert actual == expected


def test_decode_call_input(contract_instance, calldata):
    method = contract_instance.setNumber.call
    actual = method.decode_input(calldata)
    expected = "setNumber(uint256)", {"num": 222}
    assert actual == expected


def test_decode_call_input_no_method_id(contract_instance, calldata):
    """
    Ensure Ape can figure out the method if the ID is missing.
    """
    anonymous_calldata = calldata[4:]
    method = contract_instance.setNumber.call
    actual = method.decode_input(anonymous_calldata)
    expected = "setNumber(uint256)", {"num": 222}
    assert actual == expected


def test_encode_transaction_input(contract_instance, calldata):
    method = contract_instance.setNumber
    actual = method.encode_input(222)
    expected = calldata
    assert actual == expected


def test_decode_transaction_input(contract_instance, calldata):
    method = contract_instance.setNumber
    actual = method.decode_input(calldata)
    expected = "setNumber(uint256)", {"num": 222}
    assert actual == expected


def test_decode_transaction_input_no_method_id(contract_instance, calldata):
    """
    Ensure Ape can figure out the method if the ID is missing.
    """
    anonymous_calldata = calldata[4:]
    method = contract_instance.setNumber
    actual = method.decode_input(anonymous_calldata)
    expected = "setNumber(uint256)", {"num": 222}
    assert actual == expected


def test_decode_input(contract_instance, calldata):
    actual = contract_instance.decode_input(calldata)
    expected = "setNumber(uint256)", {"num": 222}
    assert actual == expected


def test_decode_ambiguous_input(solidity_contract_instance, calldata_with_address):
    anonymous_calldata = calldata_with_address[4:]
    method = solidity_contract_instance.setNumber
    expected = (
        f"Unable to find matching method ABI for calldata '{anonymous_calldata.hex()}'. "
        "Try prepending a method ID to the beginning of the calldata."
    )
    with pytest.raises(ContractError, match=expected):
        method.decode_input(anonymous_calldata)


def test_is_contract(contract_instance):
    assert contract_instance.is_contract


def test_is_contract_when_code_is_str(mock_provider, owner):
    """
    Tests the cases when an ecosystem uses str for ContractCode.
    """
    # Set up the provider to return str instead of HexBytes for code.
    mock_provider._web3.eth.get_code.return_value = "0x123"
    assert owner.is_contract

    # When the return value is the string "0x", it should not code as having code.
    mock_provider._web3.eth.get_code.return_value = "0x"
    assert not owner.is_contract


def test_obj_as_struct_input(contract_instance, owner, data_object):
    assert contract_instance.setStruct(data_object) is None


def test_dict_as_struct_input(contract_instance, owner):
    data = {"a": owner, "b": HexBytes(123), "c": "GETS IGNORED"}
    assert contract_instance.setStruct(data) is None


def test_obj_list_as_struct_array_input(contract_instance, owner, data_object):
    assert contract_instance.setStructArray([data_object, data_object]) is None


def test_dict_list_as_struct_array_input(contract_instance, owner):
    data = {"a": owner, "b": HexBytes(123), "c": "GETS IGNORED"}
    assert contract_instance.setStructArray([data, data]) is None


def test_custom_error(error_contract, not_owner):
    contract = error_contract
    unauthorized = contract.Unauthorized
    assert issubclass(unauthorized, CustomError)

    with pytest.raises(contract.Unauthorized) as err:
        contract.withdraw(sender=not_owner)

    assert err.value.inputs == {"addr": not_owner.address, "counter": 123}


def test_get_error_by_signature(error_contract):
    """
    Helps in cases where multiple errors have same name.
    Only happens when importing or using types from interfaces.
    """
    signature = error_contract.Unauthorized.abi.signature
    actual = error_contract.get_error_by_signature(signature)
    expected = error_contract.Unauthorized
    assert actual == expected


def test_source_path(project_with_contract, owner):
    contracts_folder = project_with_contract.contracts_folder
    contract = project_with_contract.contracts["Contract"]
    contract_instance = owner.deploy(project_with_contract.get_contract("Contract"))
    expected = contracts_folder / contract.source_id

    assert contract_instance.source_path.is_file()
    assert contract_instance.source_path == expected


def test_fallback(fallback_contract, owner):
    """
    Test that shows __call__ uses the contract's defined fallback method.
    We know this is a successful test because otherwise you would get a
    ContractLogicError.
    """
    receipt = fallback_contract(sender=owner, gas=40000, data="0x123")
    assert not receipt.failed


def test_value_to_non_payable_fallback_and_no_receive(
    vyper_fallback_contract, owner, vyper_fallback_contract_type
):
    """
    Test that shows when fallback is non-payable and there is no receive,
    and you try to send a value, it fails.
    """
    # Hack to set fallback as non-payable.
    contract_type_data = vyper_fallback_contract_type.dict()
    for abi in contract_type_data["abi"]:
        if abi.get("type") == "fallback":
            abi["stateMutability"] = "non-payable"
            break

    new_contract_type = ContractType.parse_obj(contract_type_data)
    contract = owner.chain_manager.contracts.instance_at(
        vyper_fallback_contract.address, contract_type=new_contract_type
    )
    expected = (
        r"Contract's fallback is non-payable and there is no receive ABI\. Unable to send value\."
    )
    with pytest.raises(ContractError, match=expected):
        contract(sender=owner, value=1)

    # Show can bypass by using `as_transaction()` and `owner.call()`.
    txn = contract.as_transaction(sender=owner, value=1)
    receipt = owner.call(txn)

    # NOTE: This actually passed because the non-payble was hacked in (see top of test).
    # The actual contract's default is payable, so the receipt actually succeeds.
    # ** Nonetheless, this test is only proving you can bypass the checks **.
    assert not receipt.failed


def test_fallback_with_data_and_value_and_receive(solidity_fallback_contract, owner):
    """
    In the case when there is a fallback method and a receive method, if the user sends data,
    it will hit the fallback method. But if they also send a value, it would fail if the fallback
    is non-payable.
    """
    expected = "Sending both value= and data= but fallback is non-payable."
    with pytest.raises(ContractError, match=expected):
        solidity_fallback_contract(sender=owner, data="0x123", value=1)

    # Show can bypass by using `as_transaction()` and `owner.call()`.
    txn = solidity_fallback_contract.as_transaction(sender=owner, data="0x123", value=1)
    with pytest.raises(ContractLogicError):
        owner.call(txn)


def test_fallback_not_defined(contract_instance, owner):
    """
    Test that shows __call__ attempts to use the Fallback method,
    which is not defined and results in a ContractLogicError.
    """

    with pytest.raises(ContractLogicError):
        # Fails because no fallback is defined in these contracts.
        contract_instance(sender=owner)


def test_fallback_as_transaction(fallback_contract, owner, eth_tester_provider):
    txn = fallback_contract.as_transaction(sender=owner)
    assert isinstance(txn, TransactionAPI)
    assert txn.sender == owner

    # Use case: estimating gas ahead of time.
    estimate = eth_tester_provider.estimate_gas_cost(txn)
    assert estimate > 0

    # Show we can send this txn.
    receipt = owner.call(txn)
    assert not receipt.failed


def test_fallback_estimate_gas_cost(fallback_contract, owner):
    estimate = fallback_contract.estimate_gas_cost(sender=owner)
    assert estimate > 0


def test_private_transaction(vyper_contract_instance, owner):
    receipt = vyper_contract_instance.setNumber(2, sender=owner, private=True)
    assert not receipt.failed


def test_private_transaction_live_network(vyper_contract_instance, owner, dummy_live_network):
    with pytest.raises(APINotImplementedError):
        vyper_contract_instance.setNumber(2, sender=owner, private=True)


def test_contract_declared_from_blueprint(
    vyper_blueprint, vyper_factory, vyper_contract_container, sender
):
    # Call the factory method that calls `create_from_blueprint()` and logs an events
    # with the resulting address. The first arg is necessary calldata.
    receipt = vyper_factory.create_contract(vyper_blueprint, 321, sender=sender)

    # Create a contract instance at this new address using the contract type
    # from the blueprint.
    address = receipt.events[-1].target
    instance = vyper_contract_container.at(address)

    # Ensure we can invoke a method on that contract.
    receipt = instance.setAddress(sender, sender=sender)
    assert not receipt.failed
