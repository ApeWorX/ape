import pytest
from packaging.version import Version

from ape.exceptions import APINotImplementedError
from ape.utils.misc import (
    add_padding_to_strings,
    extract_nested_value,
    get_package_version,
    raises_not_implemented,
    run_until_complete,
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
