from ape.utils.misc import add_padding_to_strings, extract_nested_value


def test_extract_nested_value():
    structure = {"foo": {"bar": {"test": "expected_value"}}}
    assert extract_nested_value(structure, "foo", "bar", "test") == "expected_value"


def test_extract_nested_value_non_dict_in_middle_returns_none():
    structure = {"foo": {"non_dict": 3, "bar": {"test": "expected_value"}}}
    assert not extract_nested_value(structure, "foo", "non_dict", "test")


def test_add_spacing_to_strings():
    string_list = ["foo", "address", "ethereum"]
    expected = ["foo         ", "address     ", "ethereum    "]
    actual = add_padding_to_strings(string_list, extra_spaces=4)
    assert actual == expected
