import pytest
from packaging.version import Version

from ape.exceptions import APINotImplementedError
from ape.utils.misc import (
    add_padding_to_strings,
    extract_nested_value,
    get_package_version,
    mergesort_iterators,
    raises_not_implemented,
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


@pytest.mark.parametrize(
    "items,result",
    [
        # NOTE: All inputs must be ordered according to key fn
        (([1], []), [1]),
        (([], [1]), [1]),
        (([1], [2]), [1, 2]),
        (([1, 3], [2]), [1, 2, 3]),
        (([1, 4], [2, 3, 5]), [1, 2, 3, 4, 5]),
        (([1], [3], [2]), [1, 2, 3]),
        (([1, 3, 4], [], [2, 5]), [1, 2, 3, 4, 5]),
    ],
)
def test_mergesort_iterators(items, result):
    iters = map(iter, items)
    assert list(mergesort_iterators(*iters)) == result
