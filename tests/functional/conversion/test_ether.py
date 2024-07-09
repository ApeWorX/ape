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
        "Type '<class 'float'>' must be one of " "[AddressType, bytes, int, Decimal, bool, str]."
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
