from typing import Iterator

import pytest

from ape.exceptions import APINotImplementedError
from ape.utils.misc import (
    add_padding_to_strings,
    cached_iterator,
    extract_nested_value,
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


def test_cached_iterator():
    class _Class:
        call_count = 0

        def __init__(self, raw_list):
            self.raw_list = raw_list

        @cached_iterator
        def iterator(self) -> Iterator:
            return self.get_list()

        def get_list(self) -> Iterator:
            self.call_count += 1
            yield from self.raw_list

    demo_class_0 = _Class([1, 2, 3])
    demo_class_1 = _Class([3, 2, 1])

    assert [i for i in demo_class_0.iterator] == [1, 2, 3]
    assert [i for i in demo_class_0.iterator] == [1, 2, 3]
    assert [i for i in demo_class_0.iterator] == [1, 2, 3]

    # Since it is cached, it should only actually get called once.
    assert demo_class_0.call_count == 1

    # This class should not have been affected by that class
    assert demo_class_1.call_count == 0
    assert [i for i in demo_class_1.iterator] == [3, 2, 1]
    assert [i for i in demo_class_1.iterator] == [3, 2, 1]


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
