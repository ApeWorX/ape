import pytest
from eth_pydantic_types import HexBytes

from ape.exceptions import ConversionError
from ape.managers.converters import HexConverter, HexIntConverter


@pytest.mark.parametrize("val", ("0xA100", "0x0A100", "0x00a100"))
def test_hex_str(convert, val):
    assert convert(val, int) == 0xA100
    assert int(convert(val, bytes).hex(), 16) == int(HexBytes(0xA100).hex(), 16)


def test_int_str(convert):
    assert convert("100", int) == 100


def test_missing_prefix(convert):
    hex_value = "A100"

    assert not HexConverter().is_convertible(hex_value)
    assert not HexIntConverter().is_convertible(hex_value)

    with pytest.raises(ConversionError):
        convert(hex_value, int)
