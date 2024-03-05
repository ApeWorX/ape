from decimal import Decimal


def test_convert_float_formatted_string_to_decimal(convert):
    test_strings = [
        ".1",
        "1.",
        "1.0",
    ]
    for test_string in test_strings:
        actual = convert(test_string, Decimal)
        assert actual == Decimal(test_string)
