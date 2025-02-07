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
