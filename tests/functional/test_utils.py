from pathlib import Path

import pytest

from ape.utils import add_padding_to_strings, extract_nested_value, get_relative_path

_TEST_DIRECTORY_PATH = Path("/This/is/a/test/")
_TEST_FILE_PATH = _TEST_DIRECTORY_PATH / "scripts" / "script.py"


def test_get_relative_path_from_project():
    actual = get_relative_path(_TEST_FILE_PATH, _TEST_DIRECTORY_PATH)
    expected = Path("scripts/script.py")
    assert actual == expected


def test_get_relative_path_given_relative_path():
    relative_script_path = Path("../deploy.py")
    with pytest.raises(ValueError) as err:
        get_relative_path(relative_script_path, _TEST_DIRECTORY_PATH)

    assert str(err.value) == "'target' must be an absolute path."

    relative_project_path = Path("../This/is/a/test")

    with pytest.raises(ValueError) as err:
        get_relative_path(_TEST_FILE_PATH, relative_project_path)

    assert str(err.value) == "'anchor' must be an absolute path."


def test_get_relative_path_same_path():
    actual = get_relative_path(_TEST_FILE_PATH, _TEST_FILE_PATH)
    assert actual == Path()


def test_get_relative_path_roots():
    root = Path("/")
    actual = get_relative_path(root, root)
    assert actual == Path()


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
