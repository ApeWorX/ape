from pathlib import Path
from tempfile import mkdtemp

import pytest  # type: ignore
from click.testing import CliRunner

from ape import config
from ape._cli import cli


@pytest.fixture(scope="session")
def runner():
    yield CliRunner()


@pytest.fixture(scope="session")
def data_folder():
    yield Path(mkdtemp())


@pytest.fixture(scope="session")
def ape_cli(data_folder):
    config.DATA_FOLDER = data_folder
    yield cli
