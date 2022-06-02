import tempfile
from pathlib import Path

import pytest

from ape.utils.os import get_all_files_in_directory, get_relative_path

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


def test_get_all_files_in_directory():
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir = Path(temp_dir)
        first_dir = temp_dir / "First"
        second_dir = temp_dir / "Second"
        second_first_dir = second_dir / "SecondFirst"
        dirs = (first_dir, second_dir, second_first_dir)
        for dir_ in dirs:
            dir_.mkdir()

        file_a = first_dir / "test.t.txt"
        file_b = second_dir / "test.txt"
        file_c = second_dir / "test2.txt"
        file_d = second_first_dir / "test.inner.txt"
        file_e = second_first_dir / "test3.txt"
        files = (file_a, file_b, file_c, file_d, file_e)
        for file in files:
            file.touch()

        all_files = get_all_files_in_directory(temp_dir)
        txt_files = get_all_files_in_directory(temp_dir, pattern=r"\w+\.txt")
        t_txt_files = get_all_files_in_directory(temp_dir, pattern=r"\w+\.t.txt")
        inner_txt_files = get_all_files_in_directory(temp_dir, pattern=r"\w+\.inner.txt")

        assert len(all_files) == 5
        assert len(txt_files) == 3
        assert len(t_txt_files) == 1
        assert len(inner_txt_files) == 1
