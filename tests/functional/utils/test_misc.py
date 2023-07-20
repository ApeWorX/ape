import pytest
from ethpm_types import HexBytes
from packaging.version import Version
from web3.types import Wei

from ape.exceptions import APINotImplementedError
from ape.utils.misc import (
    ZERO_ADDRESS,
    add_padding_to_strings,
    extract_nested_value,
    get_package_version,
    is_evm_precompile,
    is_zero_hex,
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


def test_add_spacing_to_strings():
    string_list = ["foo", "address", "ethereum"]
    expected = ["foo         ", "address     ", "ethereum    "]
    actual = add_padding_to_strings(string_list, extra_spaces=4)
    assert actual == expected


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

    actual = run_until_complete(foo())
    assert actual == 3


def test_run_until_complete_multiple_coroutines():
    async def foo():
        return 3

    async def bar():
        return 4

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
