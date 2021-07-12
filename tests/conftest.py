from pathlib import Path
from tempfile import mkdtemp

import pytest  # type: ignore

import ape

# NOTE: Ensure that we don't use local paths for these
ape.config.DATA_FOLDER = Path(mkdtemp())
ape.config.PROJECT_FOLDER = Path(mkdtemp())


@pytest.fixture(scope="session")
def config():
    yield ape.config


@pytest.fixture(scope="session")
def data_folder(config):
    yield config.DATA_FOLDER


@pytest.fixture(scope="session")
def plugin_manager():
    yield ape.plugin_manager


@pytest.fixture(scope="session")
def accounts():
    yield ape.accounts


@pytest.fixture(scope="session")
def compilers():
    yield ape.compilers


@pytest.fixture(scope="session")
def networks():
    yield ape.networks


@pytest.fixture(scope="session")
def project_folder(config):
    yield config.PROJECT_FOLDER


@pytest.fixture(scope="session")
def project(config):
    yield ape.Project(config.PROJECT_FOLDER)
