import pytest
from eth_pydantic_types import HexBytes
from eth_utils import to_hex

from ape.managers.converters import HexIterableConverter


@pytest.mark.parametrize("val", ("0xA100", "0x0A100", "0x00a100", "00a100"))
def test_hex_str(convert, val):
    assert int(to_hex(convert(val, bytes)), 16) == int(to_hex(0xA100), 16)


@pytest.mark.parametrize("val", ("0xA100", "0x0A100", "0x00a100"))
def test_hex_int(convert, val):
    assert convert(val, int) == 0xA100


@pytest.mark.parametrize(
    "calldata,expected",
    (
        (
            ["0x123456", "0xabcd"],
            "0x123456abcd",
        ),
        (
            [HexBytes("0x123456"), "0xabcd"],
            "0x123456abcd",
        ),
        (
            ("0x123456", "0xabcd"),
            "0x123456abcd",
        ),
    ),
)
def test_hex_concat(calldata, expected, convert):
    assert HexIterableConverter().is_convertible(calldata)
    assert convert(calldata, bytes) == HexBytes(expected)
