from pathlib import Path

import pytest

from ape.utils import get_relative_path

_TEST_PROJECT_PATH = Path("/Users/koko/ApeProjects/koko-token/")
_TEST_SCRIPT_PATH = _TEST_PROJECT_PATH / "scripts" / "deploy.py"


def test_get_relative_path_from_project():
    actual = get_relative_path(_TEST_SCRIPT_PATH, _TEST_PROJECT_PATH)
    expected = Path("scripts/deploy.py")
    assert actual == expected


def test_get_relative_path_given_relative_path():
    relative_script_path = Path("../deploy.py")
    with pytest.raises(ValueError) as err:
        get_relative_path(relative_script_path, _TEST_PROJECT_PATH)

    assert str(err.value) == "'target' must be an absolute path"

    relative_project_path = Path("../ApeProjects/koko-token")

    with pytest.raises(ValueError) as err:
        get_relative_path(_TEST_SCRIPT_PATH, relative_project_path)

    assert str(err.value) == "'anchor' must be an absolute path"


def test_get_relative_path_same_path():
    actual = get_relative_path(_TEST_SCRIPT_PATH, _TEST_SCRIPT_PATH)
    assert actual == Path()


def test_get_relative_path_roots():
    root = Path("/")
    actual = get_relative_path(root, root)
    assert actual == Path()
