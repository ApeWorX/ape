from decimal import Decimal

import pytest


def test_converting_formatted_float_strings_to_decimal(convert):
    test_strings = ["1.000", "1.00", "1.0", "0.1", "0.01", "0.001"]
    for test_string in test_strings:
        actual = convert(test_string, Decimal)
        assert actual == Decimal(test_string)


def test_converting_badly_formatted_float_strings_to_decimal(convert):
    test_strings = [
        ".1",
        "1.",
        "1",
        ".",
    ]
    for test_string in test_strings:
        with pytest.raises(Exception):
            convert(test_string, Decimal)
