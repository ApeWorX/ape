import pytest  # type: ignore
from click.testing import CliRunner

from ape._cli import cli


@pytest.fixture(scope="session")
def runner():
    yield CliRunner()


@pytest.fixture(scope="session")
def ape_cli():
    yield cli
