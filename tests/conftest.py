from pathlib import Path
from tempfile import mkdtemp

import pytest  # type: ignore

import ape
from ape import Project
from ape import config as ape_config

TEMP_FOLDER = Path(mkdtemp())
# NOTE: Don't change this setting
ape_config.DATA_FOLDER = TEMP_FOLDER / ".ape"
# NOTE: Ensure that a temp path is used by default (avoids `.build` appearing in src)
ape_config.PROJECT_FOLDER = TEMP_FOLDER
ape.project = Project(TEMP_FOLDER)


@pytest.fixture(scope="session")
def config():
    yield ape_config


@pytest.fixture(scope="session")
def plugin_manager():
    from ape import plugin_manager

    yield plugin_manager


@pytest.fixture(scope="session")
def accounts():
    from ape import accounts

    yield accounts


@pytest.fixture(scope="session")
def compilers():
    from ape import compilers

    yield compilers


@pytest.fixture(scope="session")
def networks():
    from ape import networks

    yield networks


@pytest.fixture(scope="session")
def project():
    yield ape.project


@pytest.fixture(scope="session")
def data_folder(config):
    yield config.DATA_FOLDER
