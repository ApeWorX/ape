from decimal import Decimal

import pytest
from eth_typing import ChecksumAddress
from hypothesis import given
from hypothesis import strategies as st

from ape.exceptions import ConversionError
from ape_ethereum._converters import ETHER_UNITS

TEN_THOUSAND_ETHER_IN_WEI = 10_000_000_000_000_000_000_000


@pytest.mark.fuzzing
@given(
    value=st.decimals(
        min_value=-(2**255),
        max_value=2**256 - 1,
        allow_infinity=False,
        allow_nan=False,
    ),
    unit=st.sampled_from(list(ETHER_UNITS.keys())),
)
def test_ether_conversions(value, unit, convert):
    currency_str = f"{value} {unit}"
    actual = convert(currency_str, int)
    expected = int(value * ETHER_UNITS[unit])
    assert actual == expected
    # Also show can compare directly with str.
    assert actual == currency_str


def test_bad_type(convert):
    with pytest.raises(ConversionError) as err:
        convert("something", float)

    expected = (
        "Type '<class 'float'>' must be one of [AddressType, bytes, int, Decimal, bool, str]."
    )
    assert str(err.value) == expected


def test_no_registered_converter(convert):
    with pytest.raises(ConversionError) as err:
        convert("something", ChecksumAddress)

    assert str(err.value) == "No conversion registered to handle 'something'."


@pytest.mark.parametrize("sep", (",", "_"))
def test_separaters(convert, sep):
    """
    Show that separates, such as commands and underscores, are OK
    in currency-string values, e.g. "10,000 ETH" is valid.
    """
    currency_str = f"10{sep}000 ETHER"
    actual = convert(currency_str, int)
    expected = TEN_THOUSAND_ETHER_IN_WEI
    assert actual == expected


@pytest.mark.parametrize(
    "val,expected",
    [
        (int(1e18), "1 ether"),
        (int(1e9), "1 gwei"),
        (1, "1 wei"),
        (int(1e6), "0.001 gwei"),
        (int(1e17), "0.1 ether"),
        (int(1e20), "100 ether"),
        (int(1e7), "0.01 gwei"),
        (int(1e14), "100,000 gwei"),
    ],
)
def test_convert_int_str(val, expected, convert):
    """
    Show that converting a Decimal to a currency string works.
    """
    actual = convert(val, str)
    assert actual == expected


@pytest.mark.parametrize(
    "val,expected",
    [
        (Decimal(1), "1 ether"),
        (Decimal(1) / Decimal(1e9), "1 gwei"),
        (Decimal(1) / Decimal(1e18), "1 wei"),
        (Decimal(1000000), "1,000,000 ether"),
        (Decimal(1) / Decimal(1000), "0.001 ether"),
        (Decimal(1) / Decimal(1e10), "0.1 gwei"),
        (Decimal(1) / Decimal(1e7), "100 gwei"),
        (Decimal(1) / Decimal(10000), "100,000 gwei"),
    ],
)
def test_convert_dec_str(val, expected, convert):
    """
    Show that converting a Decimal to a currency string works.
    """
    actual = convert(val, str)
    assert actual == expected
