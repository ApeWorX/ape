import pytest  # type: ignore
from ape_ethereum.converters import ETHER_UNITS
from eth_typing import ChecksumAddress
from hypothesis import given
from hypothesis import strategies as st

from ape import convert
from ape.exceptions import ConversionError


@pytest.mark.fuzzing
@given(
    value=st.decimals(
        min_value=-(2 ** 255),
        max_value=2 ** 256 - 1,
        allow_infinity=False,
        allow_nan=False,
    ),
    unit=st.sampled_from(list(ETHER_UNITS.keys())),
)
def test_ether_conversions(value, unit):
    actual = convert(value=f"{value} {unit}", type=int)
    expected = int(value * ETHER_UNITS[unit])
    assert actual == expected


def test_bad_type():
    with pytest.raises(ConversionError) as err:
        convert(value="something", type=float)

    expected = "Type '<class 'float'>' must be one of [ChecksumAddress, bytes, int]"
    assert str(err.value) == expected


def test_no_registered_converter():
    with pytest.raises(ConversionError) as err:
        convert(value="something", type=ChecksumAddress)

    assert str(err.value) == "No conversion registered to handle 'something'"
