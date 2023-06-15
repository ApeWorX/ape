import pytest
from ethpm_types import HexBytes

from ape.exceptions import ConversionError
from ape.managers.converters import HexConverter, HexIntConverter


def test_hex_str(convert):
    hex_value = "0xA100"
    int_str_value = "100"
    hex_expected = 41216
    int_expected = 100
    assert convert(hex_value, int) == hex_expected
    assert convert(int_str_value, int) == int_expected
    assert convert(hex_value, bytes) == HexBytes(hex_value)
    assert convert(int_expected, bytes) == HexBytes(int_expected)


def test_missing_prefix(convert):
    hex_value = "A100"

    assert not HexConverter().is_convertible(hex_value)
    assert not HexIntConverter().is_convertible(hex_value)

    with pytest.raises(ConversionError):
        convert(hex_value, int)
