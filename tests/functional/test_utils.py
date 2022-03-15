from pathlib import Path

import pytest

from ape.types import AddressType
from ape.utils import extract_nested_value, get_relative_path, to_address

_TEST_DIRECTORY_PATH = Path("/This/is/a/test/")
_TEST_FILE_PATH = _TEST_DIRECTORY_PATH / "scripts" / "script.py"
_TEST_ADDRESS_LENGTH_42 = "0x1e59ce931B4CFea3fe4B875411e280e173cB7A9C"
_TEST_ADDRESS_LENGTH_65 = "0x3371cA9a145A2168095bA668F9032E32A36257bEbb8f19B324953BdfAbF986D"


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


@pytest.mark.parametrize(
    "address,expected",
    [
        (_TEST_ADDRESS_LENGTH_42, _TEST_ADDRESS_LENGTH_42),
        (_TEST_ADDRESS_LENGTH_42.lower(), _TEST_ADDRESS_LENGTH_42),
        (int(_TEST_ADDRESS_LENGTH_42, 16), _TEST_ADDRESS_LENGTH_42),
        (_TEST_ADDRESS_LENGTH_65, _TEST_ADDRESS_LENGTH_65),
        (_TEST_ADDRESS_LENGTH_65.lower(), _TEST_ADDRESS_LENGTH_65),
        (int(_TEST_ADDRESS_LENGTH_65, 16), _TEST_ADDRESS_LENGTH_65),
    ],
)
def test_to_address_length_42(address, expected):
    assert to_address(address) == AddressType(expected)  # type: ignore
