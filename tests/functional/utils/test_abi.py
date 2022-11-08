import pytest
from hypothesis import given, strategies

from ape.utils import parse_type


def test_parse_type_simple():
    assert parse_type({"type": "int"}) == "int"


def test_parse_type_simple_array():
    assert parse_type({"type": "int[]"}) == ["int"]


def test_parse_type_simple_tuple():
    assert parse_type({"type": "tuple", "components": [{"type": "int"}]}) == ("int",)


def test_parse_type_simple_tuple_array():
    assert parse_type({"type": "tuple", "components": [{"type": "int[]"}]}) == (["int"],)


def test_parse_type_advanced_tuple():
    assert parse_type(
        {
            "type": "tuple",
            "components": [{"type": "tuple[]", "components": [{"type": "int[]"}]}, {"type": "int"}],
        }
    ) == ([(["int"],)], "int")
