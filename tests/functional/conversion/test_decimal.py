from decimal import Decimal

import pytest

from ape.exceptions import ConversionError


def test_convert_formatted_float_strings_to_decimal(convert):
    test_strings = [
        "1.000",
        "1.00",
        "1.0",
        "0.1",
        "0.01",
        "0.001",
    ]
    for test_string in test_strings:
        actual = convert(test_string, Decimal)
        assert actual == Decimal(test_string)


def test_convert_badly_formatted_float_strings_to_decimal(convert):
    test_strings = [
        ".1",
        "1.",
        ".",
    ]
    for test_string in test_strings:
        with pytest.raises(
            ConversionError, match=f"No conversion registered to handle '{test_string}'"
        ):
            convert(test_string, Decimal)


def test_convert_int_strings(convert):
    test_strings = [
        "1",
        "10",
        "100",
    ]
    for test_string in test_strings:
        with pytest.raises(
            ConversionError, match=f"No conversion registered to handle '{test_string}'"
        ):
            convert(test_string, Decimal)


def test_convert_alphanumeric_strings(convert):
    test_strings = [
        "a",
        "H",
        "XYZ",
    ]
    for test_string in test_strings:
        with pytest.raises(
            ConversionError, match=f"No conversion registered to handle '{test_string}'"
        ):
            convert(test_string, Decimal)


def test_convert_strings_with_token_names(convert):
    test_strings = [
        "0.999 DAI",
        "10.0 USDC",
    ]
    for test_string in test_strings:
        with pytest.raises(
            ConversionError, match=f"No conversion registered to handle '{test_string}'"
        ):
            convert(test_string, Decimal)


def test_convert_strings_with_ether_alias(convert):
    test_strings = [
        "0 wei",
        "999 gwei",
        "1.0 ether",
    ]
    for test_string in test_strings:
        with pytest.raises(
            ConversionError, match=f"No conversion registered to handle '{test_string}'"
        ):
            convert(test_string, Decimal)
