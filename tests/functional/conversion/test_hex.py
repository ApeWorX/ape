import pytest

from ape import chain


def test_hex_str():
    hex_value = "0xA100"
    int_value = "100"
    hex_expected = 41216
    int_expected = 100
    assert chain.conversion_manager.convert(hex_value, int) == hex_expected
    assert chain.conversion_manager.convert(int_value, int) == int_expected


def test_missing_prefix():
    hex_value = "A100"
    with pytest.raises(ValueError):
        chain.conversion_manager.convert(hex_value, int)
