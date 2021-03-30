from pathlib import Path
from tempfile import mkdtemp

import pytest  # type: ignore
from click.testing import CliRunner

import ape
from ape._cli import cli


@pytest.fixture(scope="session")
def runner():
    yield CliRunner()


@pytest.fixture(scope="session")
def data_folder():
    yield Path(mkdtemp())


@pytest.fixture(scope="session")
def ape_cli(data_folder):
    ape.DATA_FOLDER = data_folder
    yield cli
