import json
from pathlib import Path
from tempfile import mkdtemp

import pytest  # type: ignore
from click.testing import CliRunner

from ape import Project, config
from ape._cli import cli


@pytest.fixture(scope="session")
def runner():
    yield CliRunner()


@pytest.fixture(scope="session")
def data_folder():
    data_folder = Path(mkdtemp())
    config.DATA_FOLDER = data_folder
    yield data_folder


@pytest.fixture(scope="session")
def project_folder():
    project_folder = Path(mkdtemp())
    config.PROJECT_FOLDER = project_folder
    yield project_folder


@pytest.fixture(scope="session")
def ape_cli():
    # TODO: Ensure cli is invoked with project_folder
    yield cli


@pytest.fixture(scope="session")
def project(project_folder):
    yield Project(project_folder)


@pytest.fixture(
    scope="session",
    params=[
        # Copied from https://github.com/ethpm/ethpm-spec/tree/master/examples
        "escrow",
        "owned",
        "piper-coin",
        "safe-math-lib",
        "standard-token",
        "transferable",
        "wallet-with-send",
        "wallet",
    ],
)
def manifest(request):
    yield json.loads((Path(__file__).parent / "manifests" / f"{request.param}.json").read_text())
