import pytest

from ape import chain
from ape.exceptions import ConversionError
from ape.managers.converters import HexConverter, HexIntConverter


def test_hex_str():
    hex_value = "0xA100"
    int_value = "100"
    hex_expected = 41216
    int_expected = 100
    assert chain.conversion_manager.convert(hex_value, int) == hex_expected
    assert chain.conversion_manager.convert(int_value, int) == int_expected


def test_missing_prefix():
    hex_value = "A100"

    assert not HexConverter().is_convertible(hex_value)
    assert not HexIntConverter().is_convertible(hex_value)

    with pytest.raises(ConversionError):
        chain.conversion_manager.convert(hex_value, int)
