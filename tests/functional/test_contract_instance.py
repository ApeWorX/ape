import re
from collections import namedtuple

import pytest
from eth_pydantic_types import HexBytes
from eth_utils import is_checksum_address, to_hex
from ethpm_types import BaseModel, ContractType
from web3._utils.abi import recursive_dict_to_namedtuple

from ape.api import TransactionAPI
from ape.contracts import ContractInstance
from ape.exceptions import (
    APINotImplementedError,
    ArgumentsLengthError,
    ChainError,
    ContractDataError,
    ContractLogicError,
    CustomError,
    MethodNonPayableError,
    ProviderNotConnectedError,
    SignatureError,
)
from ape.types.address import AddressType
from ape_ethereum.transactions import TransactionStatusEnum, TransactionType

MATCH_TEST_CONTRACT = re.compile(r"<TestContract((Sol)|(Vy))")


@pytest.fixture
def data_object(owner):
    class DataObject(BaseModel):
        a: AddressType = owner.address
        b: HexBytes = HexBytes(123)
        c: int = 888
        # Showing that extra keys don't matter.
        extra_key: str = "GETS IGNORED"

    return DataObject()


def test_contract_interaction(eth_tester_provider, owner, vyper_contract_instance, mocker):
    """
    Small integration test with varied contract interaction.
    """

    # Spy on the estimate_gas RPC method.
    estimate_gas_spy = mocker.spy(eth_tester_provider.web3.eth, "estimate_gas")

    # Check what max gas is before transacting.
    max_gas = eth_tester_provider.max_gas

    # Invoke a method from a contract via transacting.
    receipt = vyper_contract_instance.setNumber(102, sender=owner)

    # Verify values from the receipt.
    assert not receipt.failed
    assert receipt.receiver == vyper_contract_instance.address
    assert receipt.gas_used < receipt.gas_limit
    assert receipt.gas_limit == max_gas

    # Show contract state changed.
    num_val = vyper_contract_instance.myNumber()
    assert num_val == 102

    # Show that numbers from contract-return values are always currency-value
    # comparable.
    assert num_val == "102 WEI"

    # Verify the estimate gas RPC was not used (since we are using max_gas).
    assert estimate_gas_spy.call_count == 0


def test_eq(vyper_contract_instance, chain):
    other = chain.contracts.instance_at(vyper_contract_instance.address)
    assert other == vyper_contract_instance


def test_transact(owner, contract_instance):
    contract_instance.setNumber(2, sender=owner)
    assert contract_instance.myNumber() == 2


def test_transact_on_a_call(vyper_contract_instance, owner):
    receipt = vyper_contract_instance.myNumber.transact(sender=owner)
    assert receipt.sender == owner
    assert receipt.status == TransactionStatusEnum.NO_ERROR


def test_transact_when_sign_false(owner, contract_instance):
    with pytest.raises(SignatureError):
        contract_instance.setNumber(2, sender=owner, sign=False)


def test_transact_wrong_number_of_arguments(owner, contract_instance):
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
def test_transact_static_fee(owner, vyper_contract_instance, type_param):
    receipt = vyper_contract_instance.setNumber(4, sender=owner, type=type_param)
    assert vyper_contract_instance.myNumber() == 4
    assert not receipt.failed
    assert receipt.type == 0


def test_transact_revert(not_owner, contract_instance):
    # 'sender' is not the owner so it will revert (with a message)
    with pytest.raises(ContractLogicError, match="!authorized") as err:
        contract_instance.setNumber(5, sender=not_owner)

    assert err.value.txn is not None


def test_transact_revert_no_message(owner, contract_instance):
    # The Contract raises empty revert when setting number to 5.
    expected = "Transaction failed."  # Default message
    with pytest.raises(ContractLogicError, match=expected) as err:
        contract_instance.setNumber(5, sender=owner)

    assert err.value.txn is not None


@pytest.mark.parametrize("gas", ("200000", 200000, "max", "auto", "0x235426"))
def test_transact_revert_specify_gas(not_owner, contract_instance, gas):
    with pytest.raises(ContractLogicError, match="!authorized") as err:
        contract_instance.setNumber(5, sender=not_owner, gas=gas)

    assert err.value.txn is not None


def test_transact_revert_no_message_specify_gas(owner, contract_instance):
    expected = "Transaction failed."  # Default message
    with pytest.raises(ContractLogicError, match=expected) as err:
        contract_instance.setNumber(5, sender=owner, gas=200000)

    assert err.value.txn is not None


def test_transact_revert_static_fee_type(not_owner, contract_instance):
    with pytest.raises(ContractLogicError, match="!authorized") as err:
        contract_instance.setNumber(5, sender=not_owner, type=0)

    assert err.value.txn is not None


def test_transact_revert_custom_exception(not_owner, error_contract):
    with pytest.raises(ContractLogicError) as err_info:
        error_contract.withdraw(sender=not_owner)

    custom_err = err_info.value
    addr = not_owner.address
    expected_message = f"addr={addr}, counter=123"
    assert custom_err.txn is not None
    assert custom_err.message == expected_message
    assert custom_err.revert_message == expected_message
    assert custom_err.inputs == {"addr": addr, "counter": 123}  # type: ignore


def test_transact_revert_allow(not_owner, contract_instance):
    # 'sender' is not the owner so it will revert (with a message)
    receipt = contract_instance.setNumber(5, sender=not_owner, raise_on_revert=False)
    assert receipt.error is not None
    assert str(receipt.error) == "!authorized"

    # Ensure this also works for calls.
    contract_instance.setNumber.call(5, raise_on_revert=False)


def test_transact_revert_handles_compiler_panic(owner, contract_instance):
    # note: setBalance is a weird name - it actually adjusts the balance.
    # first, set it to be 1 less than an overflow.
    contract_instance.setBalance(owner, 2**256 - 1, sender=owner)
    # then, add 1 more, so it should no overflow and cause a compiler panic.
    with pytest.raises(ContractLogicError):
        contract_instance.setBalance(owner, 1, sender=owner)


def test_transact_private(vyper_contract_instance, owner):
    receipt = vyper_contract_instance.setNumber(2, sender=owner, private=True)
    assert not receipt.failed


def test_transact_private_live_network(vyper_contract_instance, owner, dummy_live_network):
    with pytest.raises(APINotImplementedError):
        vyper_contract_instance.setNumber(2, sender=owner, private=True)


@pytest.mark.parametrize(
    "calldata,expected",
    (
        (
            "0x123456",
            "0x123456",
        ),
        (
            HexBytes("0x123456"),
            "0x123456",
        ),
        (
            ["0x123456", "0xabcd"],
            "0x123456abcd",
        ),
        (
            [HexBytes("0x123456"), "0xabcd"],
            "0x123456abcd",
        ),
        (
            ("0x123456", "0xabcd"),
            "0x123456abcd",
        ),
    ),
)
def test_transact_calldata_arg(calldata, expected, contract_instance, owner):
    """
    Tests invoking a method with argument of type `bytes calldata data` (Solidity).
    """
    tx = contract_instance.functionWithCalldata(calldata, sender=owner)
    assert not tx.failed
    assert HexBytes(expected) in tx.data


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
def test_transact_specify_gas(vyper_contract_instance, owner, gas_kwarg):
    gas = 400000
    kwargs = {"sender": owner, gas_kwarg: gas}
    receipt = vyper_contract_instance.setNumber(222, **kwargs)
    assert not receipt.failed
    assert receipt.gas_limit == gas


def test_call(vyper_contract_instance):
    """
    By default, calls returndata gets decoded into Python types.
    """
    result = vyper_contract_instance.myNumber()
    assert isinstance(result, int)


def test_call_transaction(contract_instance, owner, chain):
    # Transaction never submitted because using `call`.
    init_block = chain.blocks[-1]
    contract_instance.setNumber.call(1, sender=owner)

    # No mining happens because it's a call
    assert init_block == chain.blocks[-1]


def test_call_revert(contract_instance):
    with pytest.raises(ContractLogicError, match="call revert"):
        contract_instance.callThatReverts()


def test_call_revert_allow(contract_instance):
    revert = contract_instance.callThatReverts(raise_on_revert=False)
    assert revert == "call revert"


def test_call_revert_allow_and_no_decode(contract_instance):
    revert = contract_instance.callThatReverts(raise_on_revert=False, decode=False)
    assert revert == HexBytes(0x63616C6C20726576657274)


def test_call_using_block_id(vyper_contract_instance, owner, chain, networks_connected_to_tester):
    contract = vyper_contract_instance
    contract.setNumber(1, sender=owner)
    height = chain.blocks.height
    contract.setNumber(33, sender=owner)
    actual = contract.myNumber(block_id=height)
    assert actual == 1


def test_call_decode_false(vyper_contract_instance):
    """
    Use decode=False to get the raw bytes returndata of a function call.
    """
    result = vyper_contract_instance.myNumber(decode=False)
    assert not isinstance(result, int)
    assert isinstance(result, bytes)


def test_call_use_block_id(contract_instance, owner, chain):
    expected = 2
    contract_instance.setNumber(expected, sender=owner)
    block_id = chain.blocks.height  # int
    contract_instance.setNumber(3, sender=owner)  # latest
    actual = contract_instance.myNumber(block_id=block_id)
    assert actual == expected

    # Ensure works with hex
    block_id = to_hex(block_id)
    actual = contract_instance.myNumber(block_id=block_id)
    assert actual == expected

    # Ensure alias "block_id" works.
    actual = contract_instance.myNumber(block_id=block_id)
    assert actual == expected

    # Ensure works keywords like "latest"
    actual = contract_instance.myNumber(block_id="latest")
    assert actual == 3


def test_call_when_disconnected(networks, vyper_contract_instance):
    """
    Was getting a strange here at one point when trying to make a call before connecting.
    This test is to ensure we get a normal error in this context.
    """
    provider = networks.active_provider
    networks.active_provider = None
    try:
        with pytest.raises(ProviderNotConnectedError):
            vyper_contract_instance.myNumber()
    finally:
        networks.active_provider = provider


def test_repr(vyper_contract_instance):
    assert re.match(
        rf"<VyperContract {vyper_contract_instance.address}>",
        repr(vyper_contract_instance),
    )
    assert (
        repr(vyper_contract_instance.setNumber)
        == f"<VyperContract {vyper_contract_instance.address}>.setNumber"
    )
    assert str(vyper_contract_instance.setNumber) == "setNumber(uint256 num)"
    assert (
        repr(vyper_contract_instance.myNumber)
        == f"<VyperContract {vyper_contract_instance.address}>.myNumber"
    )
    assert str(vyper_contract_instance.myNumber) == "myNumber() -> uint256"
    assert (
        repr(vyper_contract_instance.NumberChange) == "NumberChange(bytes32 b, uint256 prevNum, "
        "string dynData, uint256 indexed newNum, string indexed dynIndexed)"
    )


def test_structs(contract_instance, owner, chain, mystruct_c):
    actual = contract_instance.getStruct()
    actual_sender, actual_prev_block, actual_c = actual
    tx_hash = chain.blocks[-2].hash

    # Expected: a == msg.sender
    assert actual.a == actual["a"] == actual[0] == actual_sender == owner
    assert is_checksum_address(actual.a)

    # Expected: b == block.prevhash.
    assert actual.b == actual["b"] == actual[1] == actual_prev_block == tx_hash
    assert isinstance(actual.b, bytes)

    # Expected: c == 244
    assert actual.c == actual["c"] == actual_c == mystruct_c == f"{mystruct_c} wei"

    expected_dict = {"a": owner, "b": tx_hash, "c": mystruct_c}
    assert actual == expected_dict

    expected_tuple = (owner, tx_hash, mystruct_c)
    assert actual == expected_tuple

    expected_list = [owner, tx_hash, mystruct_c]
    assert actual == expected_list

    expected_struct = contract_instance.getStruct()
    assert actual == expected_struct


def test_structs_nested(contract_instance, owner, chain, mystruct_c):
    actual_1 = contract_instance.getNestedStruct1()
    actual_2 = contract_instance.getNestedStruct2()
    actual_sender_1, actual_prev_block_1, actual_c_1 = actual_1.t
    actual_sender_2, actual_prev_block_2, actual_c_2 = actual_2.t

    # Expected: t.a == msg.sender
    assert actual_1.t.a == actual_1.t["a"] == actual_1.t[0] == actual_sender_1 == owner
    assert is_checksum_address(actual_1.t.a)
    assert is_checksum_address(actual_sender_1)
    assert actual_1.foo == 1
    assert actual_2.t.a == actual_2.t["a"] == actual_2.t[0] == actual_sender_2 == owner
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
    assert isinstance(actual_1.t.b, bytes)
    assert isinstance(actual_1.t.b, HexBytes)
    assert (
        actual_2.t.b
        == actual_2.t["b"]
        == actual_2.t[1]
        == actual_prev_block_2
        == chain.blocks[-2].hash
    )
    assert isinstance(actual_2.t.b, bytes)
    assert isinstance(actual_2.t.b, HexBytes)

    # Expected: t.c == 244
    assert actual_c_1 == actual_c_2 == mystruct_c == f"{mystruct_c} wei"


def test_structs_nested_in_tuples(contract_instance, owner):
    result_1 = contract_instance.getNestedStructWithTuple1()
    struct_1 = result_1[0]
    assert result_1[1] == 1
    assert struct_1.foo == 1
    assert struct_1.t.a == owner
    assert is_checksum_address(struct_1.t.a)

    result_2 = contract_instance.getNestedStructWithTuple2()
    struct_2 = result_2[1]
    assert result_2[0] == 2
    assert struct_2.foo == 2
    assert struct_2.t.a == owner
    assert is_checksum_address(struct_2.t.a)


def test_structs_in_empty_dyn_array(contract_instance):
    actual = contract_instance.getEmptyDynArrayOfStructs()
    expected: list = []
    assert actual == expected


def test_structs_in_empty_tuple_of_dyn_array(contract_instance):
    actual = contract_instance.getEmptyTupleOfDynArrayStructs()
    expected: tuple[list, list] = ([], [])
    assert actual == expected


def test_structs_in_empty_tuple_of_array_of_structs_and_dyn_array(
    contract_instance,
    zero_address,
):
    actual = contract_instance.getEmptyTupleOfArrayOfStructsAndDynArrayOfStructs()

    # empty address, bytes, and int.
    expected_fixed_array = (
        zero_address,
        HexBytes("0x0000000000000000000000000000000000000000000000000000000000000000"),
        0,
    )

    assert actual[0] == [expected_fixed_array, expected_fixed_array, expected_fixed_array]
    assert actual[1] == []


def test_structs_in_tuple_of_int_and_struct_array(contract_instance):
    actual_int, actual_struct_array = contract_instance.getTupleOfIntAndStructArray()
    assert actual_int == 0
    assert len(actual_struct_array) == 5
    assert len(actual_struct_array[0]) == 6


def test_structs_get_empty_tuple_of_int_and_dyn_array(contract_instance):
    actual = contract_instance.getEmptyTupleOfIntAndDynArray()
    expected: tuple[list, list] = ([], [])
    assert actual == expected


def test_structs_from_vyper_with_array(vyper_contract_instance):
    # NOTE: Vyper struct arrays <=0.3.3 don't include struct info
    actual = vyper_contract_instance.getStructWithArray()
    assert actual.foo == 1
    assert actual.bar == 2
    assert len(actual.arr) == 2


def test_structs_from_solidity_with_array(solidity_contract_instance, owner):
    actual = solidity_contract_instance.getStructWithArray()
    assert actual.foo == 1
    assert actual.bar == 2
    assert len(actual.arr) == 2, "Unexpected array length"
    assert actual.arr[0].a == owner
    assert is_checksum_address(actual.arr[0].a)


def test_structs_in_vyper_arrays(vyper_contract_instance, owner):
    # NOTE: Vyper struct arrays <=0.3.3 don't include struct info
    actual_dynamic = vyper_contract_instance.getDynamicStructArray()
    assert len(actual_dynamic) == 2
    assert actual_dynamic[0][0][0] == owner
    assert is_checksum_address(actual_dynamic[0][0][0])
    assert actual_dynamic[0][1] == 1
    assert actual_dynamic[1][0][0] == owner
    assert is_checksum_address(actual_dynamic[1][0][0])
    assert actual_dynamic[1][1] == 2

    actual_static = vyper_contract_instance.getStaticStructArray()
    assert len(actual_static) == 2
    assert actual_static[0][0] == 1
    assert actual_static[0][1][0] == owner
    assert is_checksum_address(actual_static[0][1][0])
    assert actual_static[1][0] == 2
    assert actual_static[1][1][0] == owner
    assert is_checksum_address(actual_static[1][1][0])


def test_structs_in_solidity_dynamic_arrays(solidity_contract_instance, owner):
    # Run test twice to make sure we can call method more than 1 time and have
    # the same result.
    for _ in range(2):
        actual_dynamic = solidity_contract_instance.getDynamicStructArray()
        assert len(actual_dynamic) == 2
        assert actual_dynamic[0].foo == 1
        assert actual_dynamic[0].t.a == owner
        assert is_checksum_address(actual_dynamic[0].t.a)

        assert actual_dynamic[1].foo == 2
        assert actual_dynamic[1].t.a == owner
        assert is_checksum_address(actual_dynamic[1].t.a)


def test_structs_in_solidity_static_arrays(solidity_contract_instance, owner):
    # Run test twice to make sure we can call method more than 1 time and have
    # the same result.
    for _ in range(2):
        actual_dynamic = solidity_contract_instance.getStaticStructArray()
        assert len(actual_dynamic) == 3
        assert actual_dynamic[0].foo == 1
        assert actual_dynamic[0].t.a == owner
        assert is_checksum_address(actual_dynamic[0].t.a)

        assert actual_dynamic[1].foo == 2
        assert actual_dynamic[1].t.a == owner
        assert is_checksum_address(actual_dynamic[1].t.a)


def test_structs_input_obj(contract_instance, owner, data_object):
    assert not contract_instance.setStruct(data_object, sender=owner).failed
    actual = contract_instance.myStruct()

    assert actual.a == data_object.a

    # B is automatically right-padded.
    expected_b = HexBytes("0x7b00000000000000000000000000000000000000000000000000000000000000")
    assert actual.b == expected_b

    assert actual.c == data_object.c


def test_structs_input_dict(contract_instance, owner):
    # NOTE: Also showing extra keys like "extra_key" don't matter and are ignored.
    data = {"a": owner, "b": HexBytes(123), "c": 999, "extra_key": "GETS_IGNORED"}
    assert not contract_instance.setStruct(data, sender=owner).failed
    actual = contract_instance.myStruct()
    assert actual.a == data["a"].address

    # B is automatically right-padded.
    expected_b = HexBytes("0x7b00000000000000000000000000000000000000000000000000000000000000")
    assert actual.b == expected_b

    assert actual.c == data["c"]


def test_structs_input_tuple(contract_instance, owner):
    # NOTE: Also showing extra keys like "extra_key" don't matter and are ignored.
    data = (owner, HexBytes(123), 999, "GES_IGNORED")
    assert not contract_instance.setStruct(data, sender=owner).failed
    actual = contract_instance.myStruct()
    assert actual.a == data[0].address

    # B is automatically right-padded.
    expected_b = HexBytes("0x7b00000000000000000000000000000000000000000000000000000000000000")
    assert actual.b == expected_b

    assert actual.c == data[2]


def test_structs_input_namedtuple(contract_instance, owner):
    # NOTE: Also showing extra keys like "extra_key" don't matter and are ignored.
    values = {"a": AddressType, "b": HexBytes, "c": int, "extra_key": int}
    MyStruct = namedtuple("MyStruct", values)  # type: ignore
    data = MyStruct(owner, HexBytes(123), 999, 0)  # type: ignore
    assert not contract_instance.setStruct(data, sender=owner).failed
    actual = contract_instance.myStruct()
    assert actual.a == owner.address

    # B is automatically right-padded.
    expected_b = HexBytes("0x7b00000000000000000000000000000000000000000000000000000000000000")
    assert actual.b == expected_b

    assert actual.c == data.c  # type: ignore


def test_structs_input_web3_named_tuple(solidity_contract_instance, owner):
    """
    Show we integrate nicely with web3 contracts notion of namedtuples.
    """
    data = {"a": solidity_contract_instance.address, "b": HexBytes(123), "c": 321}
    w3_named_tuple = recursive_dict_to_namedtuple(data)
    assert not solidity_contract_instance.setStruct(w3_named_tuple, sender=owner).failed

    actual = solidity_contract_instance.myStruct()
    assert actual.a == solidity_contract_instance.address

    # B is automatically right-padded.
    expected_b = HexBytes("0x7b00000000000000000000000000000000000000000000000000000000000000")
    assert actual.b == expected_b

    assert actual.c == data["c"]


@pytest.mark.parametrize("sequence_type", (list, tuple))
def test_structs_in_arrays_when_given_obj_list(contract_instance, data_object, sequence_type):
    parameter = sequence_type([data_object, data_object])
    actual = contract_instance.setStructArray(parameter)
    # The function is pure and doesn't return anything.
    # (only testing input handling).
    assert actual is None


@pytest.mark.parametrize("sequence_type", (list, tuple))
def test_structs_in_arrays_when_given_dict_list(contract_instance, owner, sequence_type):
    # NOTE: Also showing extra keys like "extra_key" don't matter and are ignored.
    data = {"a": owner, "b": HexBytes(123), "c": 444, "extra_key": "GETS IGNORED"}
    parameter = sequence_type([data, data])
    actual = contract_instance.setStructArray(parameter)
    # The function is pure and doesn't return anything.
    # (only testing input handling).
    assert actual is None


def test_arrays(contract_instance):
    assert contract_instance.getEmptyArray() == []
    assert contract_instance.getSingleItemArray() == [1]
    assert contract_instance.getFilledArray() == [1, 2, 3]


def test_arrays_of_addresses(contract_instance, owner):
    actual = contract_instance.getAddressArray()
    assert actual == [owner, owner]
    assert is_checksum_address(actual[0])
    assert is_checksum_address(actual[1])


def test_arrays_with_bigger_size(contract_instance):
    # Tests against bug where if array had size > 9, it would fail to parse.
    # Method set to return an array of size 20
    actual = contract_instance.getArrayWithBiggerSize()
    assert actual == [0] * 20


def test_arrays_in_tuple(contract_instance):
    actual = contract_instance.getTupleOfArrays()
    assert actual == ([0] * 20, [0] * 20)


def test_arrays_of_nested_fixed_fixed_arrays(contract_instance):
    """
    Return type: uint256[2][3] memory
    """
    actual = contract_instance.getNestedArrayFixedFixed()
    assert actual == [[1, 2], [3, 4], [5, 6]]


def test_arrays_of_nested_dynamic_fixed_arrays(contract_instance, owner):
    """
    Return type: uint256[2][]
    """
    actual = contract_instance.getNestedArrayDynamicFixed()
    assert actual == [[1, 2], [3, 4], [5, 6]]


def test_arrays_of_nested_fixed_dynamic(contract_instance, owner):
    """
    Return type: uint256[][3]
    """
    contract_instance.loadArrays(sender=owner)
    actual = contract_instance.getNestedArrayFixedDynamic()
    assert actual == [[0], [0, 1], [0, 1, 2]]


def test_arrays_of_nested_mixed_dynamic_arrays(contract_instance, owner):
    """
    Return type: uint256[][3][][5]
    """
    contract_instance.loadArrays(sender=owner)
    actual = contract_instance.getNestedArrayMixedDynamic()
    assert len(actual) == 5
    assert len(actual[0]) == 1
    assert len(actual[1]) == 2
    assert actual[0][0] == [[0], [0, 1], [0, 1, 2]]
    assert actual[1][0] == [[0], [0, 1], [0, 1, 2]]
    assert actual[1][1] == [[0], [0, 1], [0, 1, 2]]
    assert actual[2] == actual[3] == actual[4] == []


def test_arrays_of_nested_address_arrays(contract_instance, owner, zero_address):
    """
    Return type: address[3][]
    """
    actual = contract_instance.getNestedAddressArray()
    assert len(actual) == 2
    assert len(actual[0]) == 3
    assert len(actual[1]) == 3
    assert actual[0] == [owner, owner, owner]
    assert actual[1] == [zero_address, zero_address, zero_address]


def test_address_given_contract_instance(contract_instance, owner):
    contract_instance.setAddress(contract_instance, sender=owner)
    assert contract_instance.theAddress() == contract_instance


def test_address_given_account(contract_instance, owner):
    contract_instance.setAddress(owner, sender=owner)
    assert contract_instance.theAddress() == owner


def test_address_given_int(contract_instance, owner):
    contract_instance.setAddress(int(owner.address, 16), sender=owner)
    assert contract_instance.theAddress() == owner


@pytest.mark.parametrize("value", ["10", "0x0a", HexBytes(10)])
def test_uint256_converts_inputs(value, owner, contract_instance):
    contract_instance.setNumber(value, sender=owner)
    assert contract_instance.myNumber() == 10


@pytest.mark.parametrize(
    "value",
    [
        "0a",
        "0x0a",
        HexBytes("0x0a"),
        AddressType("0x0a"),  # type: ignore
    ],
)
def test_bytes32_converts_inputs(value, contract_instance, owner):
    contract_instance.setBytes32(value, sender=owner)

    # By default, Solidity/Vyper right-pad bytes32 values.
    expected = HexBytes("0x0a00000000000000000000000000000000000000000000000000000000000000")

    assert contract_instance.myBytes32() == expected


def test_namedtuple_from_solidity(solidity_contract_instance):
    actual = solidity_contract_instance.getNamedSingleItem()
    assert actual == 123

    actual = solidity_contract_instance.getTupleAllNamed()
    assert actual == (123, 321)
    assert actual.foo == 123
    assert actual.bar == 321

    actual = solidity_contract_instance.getPartiallyNamedTuple()
    assert actual == (123, 321)


def test_namedtuple_from_vyper(vyper_contract_instance):
    actual = vyper_contract_instance.getMultipleValues()
    assert actual == (123, 321)


def test_tuple(contract_instance):
    actual = contract_instance.getUnnamedTuple()
    assert actual == (0, 0)


def test_tuple_of_address_array(contract_instance, zero_address):
    actual = contract_instance.getTupleOfAddressArray()
    assert len(actual) == 2
    assert len(actual[0]) == 20
    assert is_checksum_address(actual[0][0])
    assert all(x == zero_address for x in actual[0][1:])
    assert actual[1] == [0] * 20


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


def test_creation_metadata(contract_instance, owner):
    assert contract_instance.creation_metadata is not None
    receipt = contract_instance.creation_metadata.receipt
    assert receipt.txn_hash == contract_instance.txn_hash
    assert receipt.contract_address == contract_instance.address
    assert receipt.sender == owner


def test_from_receipt_when_receipt_not_deploy(contract_instance, owner):
    receipt = contract_instance.setNumber(555, sender=owner)
    expected_err = (
        "Receipt missing 'contract_address' field. "
        "Was this from a deploy transaction (e.g. `project.MyContract.deploy()`)?"
    )
    with pytest.raises(ChainError, match=expected_err):
        ContractInstance.from_receipt(receipt, contract_instance.contract_type)


def test_dir(vyper_contract_instance):
    actual = dir(vyper_contract_instance)
    expected = [
        # From base class
        "address",
        "balance",
        "call_view_method",
        "code",
        "contract_type",
        "codesize",
        "creation_metadata",
        "decode_input",
        "get_event_by_signature",
        "invoke_transaction",
        "is_contract",
        "nonce",
        "provider",
        "txn_hash",
        *vyper_contract_instance._events_,
        *vyper_contract_instance._mutable_methods_,
        *vyper_contract_instance._view_methods_,
    ]
    assert sorted(actual) == sorted(expected)


def test_encode_input_call(contract_instance, calldata):
    method = contract_instance.setNumber.call
    actual = method.encode_input(222)
    expected = calldata
    assert actual == expected


def test_encode_input_transaction(contract_instance, calldata):
    method = contract_instance.setNumber
    actual = method.encode_input(222)
    expected = calldata
    assert actual == expected


def test_decode_input_call(contract_instance, calldata):
    method = contract_instance.setNumber.call
    actual = method.decode_input(calldata)
    expected = "setNumber(uint256)", {"num": 222}
    assert actual == expected


def test_decode_input_transaction(contract_instance, calldata):
    method = contract_instance.setNumber
    actual = method.decode_input(calldata)
    expected = "setNumber(uint256)", {"num": 222}
    assert actual == expected


def test_decode_input_call_without_method_id(contract_instance, calldata):
    """
    Ensure Ape can figure out the method if the ID is missing.
    """
    anonymous_calldata = calldata[4:]
    method = contract_instance.setNumber.call
    actual = method.decode_input(anonymous_calldata)
    expected = "setNumber(uint256)", {"num": 222}
    assert actual == expected


def test_decode_input_transaction_without_method_id(contract_instance, calldata):
    """
    Ensure Ape can figure out the method if the ID is missing.
    """
    anonymous_calldata = calldata[4:]
    method = contract_instance.setNumber
    actual = method.decode_input(anonymous_calldata)
    expected = "setNumber(uint256)", {"num": 222}
    assert actual == expected


def test_decode_input_ambiguous(solidity_contract_instance, calldata_with_address):
    anonymous_calldata = calldata_with_address[4:]
    method = solidity_contract_instance.setNumber
    expected = (
        f"Unable to find matching method ABI for calldata '{to_hex(anonymous_calldata)}'. "
        "Try prepending a method ID to the beginning of the calldata."
    )
    with pytest.raises(ContractDataError, match=expected):
        method.decode_input(anonymous_calldata)


def test_is_contract(contract_instance):
    assert contract_instance.is_contract


def test_is_contract_when_code_is_str(mock_provider, owner):
    """
    Tests the cases when an ecosystem uses str for ContractCode.
    """
    # Set up the provider to return str instead of HexBytes for code.
    mock_provider._web3.eth.get_code.return_value = "0x1234"
    assert owner.is_contract

    # When the return value is the string "0x", it should not code as having code.
    mock_provider._web3.eth.get_code.return_value = "0x"
    assert not owner.is_contract


def test_custom_error(error_contract, not_owner):
    contract = error_contract
    unauthorized = contract.Unauthorized
    assert issubclass(unauthorized, CustomError)

    with pytest.raises(contract.Unauthorized) as err:
        contract.withdraw(sender=not_owner)

    assert err.value.inputs == {"addr": not_owner.address, "counter": 123}


def test_custom_error_info(project, owner, error_contract):
    missing_doc_err = error_contract.Unauthorized
    empty_info = missing_doc_err.info
    assert empty_info == ""

    # NOTE: deploying a new contract to eliminate clashing with other tests.
    new_sol_contract = owner.deploy(project.SolidityContract, 26262626262)
    error_with_doc = new_sol_contract.ACustomError
    actual = error_with_doc.info
    expected = """
ACustomError()
  @details This is a doc for an error
""".strip()
    assert actual == expected


def test_get_error_by_signature(error_contract):
    """
    Helps in cases where multiple errors have same name.
    Only happens when importing or using types from interfaces.
    """
    signature = error_contract.Unauthorized.abi.signature
    actual = error_contract.get_error_by_signature(signature)
    expected = error_contract.Unauthorized
    assert actual == expected


def test_selector_identifiers(vyper_contract_instance):
    assert len(vyper_contract_instance.selector_identifiers.keys()) >= 54
    assert vyper_contract_instance.selector_identifiers["balances(address)"] == "0x27e235e3"
    assert vyper_contract_instance.selector_identifiers["owner()"] == "0x8da5cb5b"
    assert (
        vyper_contract_instance.selector_identifiers["FooHappened(uint256)"]
        == "0x1a7c56fae0af54ebae73bc4699b9de9835e7bb86b050dff7e80695b633f17abd"
    )


def test_identifier_lookup(vyper_contract_instance):
    assert len(vyper_contract_instance.identifier_lookup.keys()) >= 54
    assert vyper_contract_instance.identifier_lookup["0x27e235e3"].selector == "balances(address)"
    assert vyper_contract_instance.identifier_lookup["0x8da5cb5b"].selector == "owner()"
    assert (
        vyper_contract_instance.identifier_lookup[
            "0x1a7c56fae0af54ebae73bc4699b9de9835e7bb86b050dff7e80695b633f17abd"
        ].selector
        == "FooHappened(uint256)"
    )


def test_source_path(project_with_contract, owner):
    contract = project_with_contract.get_contract("Contract")
    instance = owner.deploy(contract)
    expected = project_with_contract.path / contract.source_id

    assert instance.source_path.is_file()
    assert instance.source_path == expected


def test_fallback(fallback_contract, owner):
    """
    Fallback contract call test.
    """
    tx = fallback_contract(sender=owner, value="1 wei")
    assert not tx.failed


def test_fallback_transaction_kwargs(fallback_contract, owner):
    """
    Test that shows __call__ uses the contract's defined fallback method.
    We know this is a successful test because otherwise you would get a
    ContractLogicError.
    """
    receipt = fallback_contract(sender=owner, gas=40000, data="0x123")
    assert not receipt.failed


def test_fallback_value_no_receive(vyper_fallback_contract, owner, project):
    """
    Test that shows when fallback is non-payable and there is no receive,
    and you try to send a value, it fails.
    """
    # Hack to set fallback as non-payable.
    contract_type_data = project.VyDefault.contract_type.model_dump()
    for abi in contract_type_data["abi"]:
        if abi.get("type") == "fallback":
            abi["stateMutability"] = "non-payable"
            break

    new_contract_type = ContractType.model_validate(contract_type_data)
    contract = owner.chain_manager.contracts.instance_at(vyper_fallback_contract.address)
    contract.contract_type = new_contract_type  # Setting to completely override instead of merge.

    expected = (
        r"Contract's fallback is non-payable and there is no receive ABI\. Unable to send value\."
    )
    with pytest.raises(MethodNonPayableError, match=expected):
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
    In the case when there is a fallback method and a `receive` method, if the user sends data,
    it will hit the fallback method. But if they also send a value, it would fail if the fallback
    is non-payable.
    """
    expected = "Sending both value= and data= but fallback is non-payable."
    with pytest.raises(MethodNonPayableError, match=expected):
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


def test_fallback_contract_as_sender(fallback_contract, owner, vyper_contract_instance):
    """
    Testing Ape's part in contract-as-a-sender. However, in this scenario, we get a `SignatureError`,
    unlike properly impersonated accounts (using providers like `ape-foundry`).
    """
    owner.transfer(fallback_contract, "1 ETH")
    with pytest.raises(SignatureError) as info:
        fallback_contract(sender=fallback_contract, value="1 wei")

    transaction = info.value.transaction
    assert transaction is not None
    assert transaction.nonce is not None  # Proves it was prepared.


def test_contract_declared_from_blueprint(vyper_blueprint, vyper_factory, project, owner):
    """
    Integration test showing how to get a contract instance from a contract deployed from
    a blueprint transaction.
    """

    # Call the factory method that calls `create_from_blueprint()` and logs an events
    # with the resulting address. The first arg is necessary calldata.
    receipt = vyper_factory.create_contract(vyper_blueprint, sender=owner)

    # Create a contract instance at this new address using the contract type
    # from the blueprint.
    address = receipt.events[-1].target
    instance = project.VyDefault.at(address)

    # Ensure we can invoke a method on that contract.
    receipt = instance(value=1, sender=owner)
    assert not receipt.failed


@pytest.mark.parametrize("tx_type", TransactionType)
def test_as_transaction(tx_type, vyper_contract_instance, owner, eth_tester_provider):
    tx = vyper_contract_instance.setNumber.as_transaction(987, sender=owner, type=tx_type.value)
    assert tx.gas_limit == eth_tester_provider.max_gas
    assert tx.sender == owner.address
    assert tx.signature is None


def test_as_transaction_sign(vyper_contract_instance, owner, eth_tester_provider):
    tx = vyper_contract_instance.setNumber.as_transaction(987, sender=owner, sign=True)
    assert tx.gas_limit == eth_tester_provider.max_gas
    assert tx.signature is not None


def test_as_transaction_bytes(vyper_contract_instance, owner, eth_tester_provider):
    signed_tx = vyper_contract_instance.setNumber.as_transaction_bytes(987, sender=owner, sign=True)
    assert isinstance(signed_tx, bytes)


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
