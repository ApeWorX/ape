from types import UnionType
from typing import Union, get_origin

import pytest

from ape.managers.converters import (
    AddressAPIConverter,
    BytesAddressConverter,
    HexConverter,
    HexIntConverter,
    IntAddressConverter,
    StringDecimalConverter,
    StringIntConverter,
)
from ape.types.address import AddressType
from ape.utils.basemodel import ManagerAccessMixin
from ape_ethereum._converters import WeiConversions

NAME_TO_CONVERTER = {
    "AddressAPI": AddressAPIConverter,
    "BytesAddress": BytesAddressConverter,
    "hex": HexConverter,
    "HexInt": HexIntConverter,
    "IntAddress": IntAddressConverter,
    "StringDecimal": StringDecimalConverter,
    "StringInt": StringIntConverter,
    "wei": WeiConversions,
}


@pytest.fixture
def conversion_manager():
    return ManagerAccessMixin.conversion_manager


@pytest.mark.parametrize("name", NAME_TO_CONVERTER)
def test_get_converter(name, conversion_manager):
    actual = conversion_manager.get_converter(name)
    expected = NAME_TO_CONVERTER[name]
    assert isinstance(actual, expected)


def test_get_converters_by_type(conversion_manager):
    converters = conversion_manager.get_converters_by_type(AddressType)
    for expected in (AddressAPIConverter, IntAddressConverter, BytesAddressConverter):
        assert any(isinstance(c, expected) for c in converters)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"gas_limit": "0x2a"},
        {"receiver": "0x0000000000000000000000000000000000000001"},
    ],
)
def test_convert_method_kwargs_unwraps_pep604_optional(monkeypatch, conversion_manager, kwargs):
    """
    Ensure `ConversionManager.convert_method_kwargs()` unwraps `X | None` annotations
    before attempting conversion (Python 3.10+ union syntax).
    """

    seen: dict[str, object] = {}

    def fake_convert(_value, to_type):
        seen["to_type"] = to_type
        return 123

    monkeypatch.setattr(conversion_manager, "convert", fake_convert)
    actual = conversion_manager.convert_method_kwargs(kwargs)

    # We attempted conversion and used the converted value.
    key = next(iter(kwargs))
    assert actual[key] == 123

    # And the chosen type is not a union (i.e. None was stripped).
    assert "to_type" in seen
    origin = get_origin(seen["to_type"])
    assert origin not in (Union, UnionType)
