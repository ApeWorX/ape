from pathlib import Path

import pytest

from ape.utils.misc import SOURCE_EXCLUDE_PATTERNS
from ape.utils.os import (
    clean_path,
    create_tempdir,
    get_all_files_in_directory,
    get_full_extension,
    get_relative_path,
    path_match,
    run_in_tempdir,
)

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
    with create_tempdir() as path:
        first_dir = path / "First"
        second_dir = path / "Second"
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

        all_files = get_all_files_in_directory(path)
        txt_files = get_all_files_in_directory(path, pattern=r"\w+\.txt", max_files=2)
        t_txt_files = get_all_files_in_directory(path, pattern=r"\w+\.t.txt")
        inner_txt_files = get_all_files_in_directory(path, pattern=r"\w+\.inner.txt")

        assert len(all_files) == 5
        assert len(txt_files) == 2
        assert len(t_txt_files) == 1
        assert len(inner_txt_files) == 1


@pytest.mark.parametrize(
    "path,expected",
    [
        ("test.json", ".json"),
        ("Contract.t.sol", ".t.sol"),
        ("this.is.a.lot.of.dots", ".is.a.lot.of.dots"),
        ("directory", ""),
        (".privateDirectory", ""),
        ("path/to/.gitkeep", ""),
        (".config.json", ".json"),
    ],
)
def test_get_full_extension(path, expected):
    path = Path(path)
    actual = get_full_extension(path)
    assert actual == expected


@pytest.mark.parametrize("name", (None, "oogabooga"))
def test_create_tempdir(name):
    with create_tempdir(name=name) as path:
        assert isinstance(path, Path)
        assert path.resolve() == path

    assert not path.is_dir()
    if name is not None:
        assert path.name == name


@pytest.mark.parametrize("name", (None, "oogabooga"))
def test_run_in_tempdir(name):
    arguments = []  # using list to make global ref work.

    def fn(p):
        arguments.append(p)

    run_in_tempdir(fn, name=name)
    assert len(arguments) == 1  # did run
    assert isinstance(arguments[0], Path)
    assert arguments[0].resolve() == arguments[0]
    if name is not None:
        assert arguments[0].name == name


@pytest.mark.parametrize(
    "path",
    (
        "path/to/.cache/file/1.json",
        Path("path/to/.cache/file/1.json"),
        ".cache",
        Path(".cache"),
        Path("contracts/.cache/TEST.json"),
    ),
)
def test_path_match_cache_folder(path):
    assert path_match(path, *SOURCE_EXCLUDE_PATTERNS)


@pytest.mark.parametrize(
    "path",
    (
        "path/to/.build/__local__.json",
        Path("path/to/.build/__local__.json"),
        ".build",
        Path(".build"),
        Path("contracts/.build/TEST.json"),
    ),
)
def test_path_match_build_folder(path):
    assert path_match(path, *SOURCE_EXCLUDE_PATTERNS)


@pytest.mark.parametrize(
    "path",
    (
        "path/to/MyFile.build.json/__local__.json",
        Path("path/to/MyFile.build.json/__local__.json"),
        ".builder",
        Path(".cacher"),
        Path("contracts/.builder/TEST.json"),
    ),
)
def test_pat_match_does_not_match_but_close(path):
    """
    Ensures we don't get false positives.
    """
    assert not path_match(path, *SOURCE_EXCLUDE_PATTERNS)


@pytest.mark.parametrize(
    "path",
    (
        ".gitkeep",
        "path/to/.gitkeep",
        "index.html",
        "path/to/index.css",
        "py.typed",
    ),
)
def test_path_match(path):
    assert path_match(path, *SOURCE_EXCLUDE_PATTERNS)


@pytest.mark.parametrize(
    "path,exc",
    [
        ("path/to/MyContract.t.sol", "*t.sol"),
        ("contracts/mocks/MyContract.sol", "mocks"),
        ("mocks/MyContract.sol", "mocks"),
        ("MockContract.sol", "Mock*"),
    ],
)
def test_path_match_test_contracts(path, exc):
    assert not path_match(path, *SOURCE_EXCLUDE_PATTERNS)
    exclusions = [*SOURCE_EXCLUDE_PATTERNS, exc]
    assert path_match(path, *exclusions)


@pytest.mark.parametrize(
    "path",
    (
        Path("path/to/contracts/exclude_dir/subdir/MyContract.json"),
        Path("exclude_dir/subdir/MyContract.json"),
        Path("exclude_dir/MyContract.json"),
    ),
)
def test_path_match_recurse_dir(path):
    """
    Testing a specific way of excluding all the files in a directory.
    """
    excl = "exclude_dir/**"
    assert path_match(path, excl)


def test_clean_path_relative_to_home():
    name = "__canary_ape_test__"
    path = Path.home() / name
    actual = clean_path(path)
    expected = f"$HOME/{name}"
    assert actual == expected


def test_clean_path_not_relative_to_home():
    name = "__canary_ape_test__"
    path = Path(name)
    actual = clean_path(path)
    assert actual == name
