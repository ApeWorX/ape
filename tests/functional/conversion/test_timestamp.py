from ape import convert


def test_convert_string_timestamp():
    time = "10-15-2021 12:15:12"
    assert convert(time, int) == 1634300112
