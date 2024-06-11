import asyncio

import pytest
from eth_pydantic_types import HexBytes
from packaging.version import Version
from web3.types import Wei

from ape.exceptions import APINotImplementedError
from ape.utils.misc import (
    ZERO_ADDRESS,
    _dict_overlay,
    add_padding_to_strings,
    extract_nested_value,
    get_package_version,
    is_evm_precompile,
    is_zero_hex,
    log_instead_of_fail,
    pragma_str_to_specifier_set,
    raises_not_implemented,
    run_until_complete,
    to_int,
)


def test_extract_nested_value():
    structure = {"foo": {"bar": {"test": "expected_value"}}}
    assert extract_nested_value(structure, "foo", "bar", "test") == "expected_value"


def test_extract_nested_value_non_dict_in_middle_returns_none():
    structure = {"foo": {"non_dict": 3, "bar": {"test": "expected_value"}}}
    assert not extract_nested_value(structure, "foo", "non_dict", "test")


def test_add_padding_to_strings():
    string_list = ["foo", "address", "ethereum"]
    expected = ["foo         ", "address     ", "ethereum    "]
    actual = add_padding_to_strings(string_list, extra_spaces=4)
    assert actual == expected


def test_add_padding_to_strings_empty_list():
    actual = add_padding_to_strings([])
    assert actual == []


def test_raises_not_implemented():
    @raises_not_implemented
    def unimplemented_api_method():
        pass

    with pytest.raises(APINotImplementedError) as err:
        unimplemented_api_method()

    assert str(err.value) == (
        "Attempted to call method 'test_raises_not_implemented.<locals>.unimplemented_api_method', "
        "method not supported."
    )
    assert isinstance(err.value, NotImplementedError)


def test_get_package_version():
    version = get_package_version("ape")
    # Fails if invalid version
    assert Version(version)


def test_run_until_complete_not_coroutine():
    expected = 3
    actual = run_until_complete(3)
    assert actual == expected


def test_run_until_complete_coroutine():
    async def foo():
        return 3

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    actual = run_until_complete(foo())
    assert actual == 3


def test_run_until_complete_multiple_coroutines():
    async def foo():
        return 3

    async def bar():
        return 4

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    actual = run_until_complete(foo(), bar())
    assert actual == [3, 4]


@pytest.mark.parametrize("addresses", [(f"0x{i}", f"0x{'0' * 39}{i}") for i in range(1, 10)])
def test_is_evm_precompile(addresses):
    for addr in addresses:
        assert is_evm_precompile(addr)


def test_is_not_evm_precompile(zero_address, owner):
    assert not is_evm_precompile(zero_address)
    assert not is_evm_precompile(owner.address)
    assert not is_evm_precompile("MyContract")


@pytest.mark.parametrize("addr", (ZERO_ADDRESS, "0x", "0x0"))
def test_is_zero_address(addr):
    assert is_zero_hex(addr)


def test_is_not_zero_address(owner):
    assert not is_zero_hex(owner.address)
    assert not is_zero_hex(owner)
    assert not is_zero_hex("MyContract")
    assert not is_zero_hex("0x01")


@pytest.mark.parametrize("val", (5, "0x5", "0x05", "0x0005", HexBytes(5), Wei(5)))
def test_to_int(val):
    assert to_int(val) == 5


@pytest.mark.parametrize(
    "spec,expected",
    [
        ("1.0", "==1.0.0"),
        ("1.0.0-beta", "==1.0.0-beta"),
        ("1.0-beta", "==1.0.0-beta"),
        ("1-beta", "==1.0.0-beta"),
        ("1.0.0-beta.1", "==1.0.0-beta.1"),
        ("1.0-beta.1", "==1.0.0-beta.1"),
        ("1-beta.1", "==1.0.0-beta.1"),
        ("~=1.0", "~=1.0"),
        (">=1", ">=1.0"),
        ("<=1.0.0-beta", "<=1.0.0-beta"),
        (">1.0-beta", ">1.0.0-beta"),
        ("1.0.0", "==1.0.0"),
        (" 1.0.0", "==1.0.0"),
        (" == 1.0.0", "==1.0.0"),
        (" = 1.0.0", "==1.0.0"),
        (">= 0.4.19 < 0.5.0", ">=0.4.19,<0.5.0"),
        (">=0.4.19,< 0.5.0", ">=0.4.19,<0.5.0"),
        (">=0.4.19 <0.5.0", ">=0.4.19,<0.5.0"),
    ],
)
def test_pragma_str_to_specifier_set(spec, expected):
    assert pragma_str_to_specifier_set(spec) == expected


def test_dict_overlay():
    mapping = {"a": 1, "b": {"one": 1, "two": 1}}
    _dict_overlay(mapping, {"a": 2, "b": {"two": 2, "three": None}, "c": {"four": 4}})

    assert mapping["a"] == 2
    assert "b" in mapping
    assert isinstance(mapping["b"], dict)
    assert "one" in mapping["b"]
    assert mapping["b"]["one"] == 1
    assert "two" in mapping["b"]
    assert mapping["b"]["two"] == 2
    assert "three" in mapping["b"]
    assert mapping["b"]["three"] is None
    assert "c" in mapping
    assert isinstance(mapping["c"], dict)
    assert "four" in mapping["c"]


def test_log_instead_of_fail(ape_caplog):
    @log_instead_of_fail()
    def my_method():
        raise ValueError("Oh no!")

    my_method()
    assert "Oh no!" in ape_caplog.head
