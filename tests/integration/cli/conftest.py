import os
from distutils.dir_util import copy_tree
from pathlib import Path

import pytest  # type: ignore
from click.testing import CliRunner

import ape
from ape import Project

TEST_PROJECTS_FOLDER = Path(__file__).parent / "data" / "projects"


@pytest.fixture(params=[p for p in TEST_PROJECTS_FOLDER.iterdir() if p.is_dir()])
def project_folder(request, config):
    project_source_dir = request.param
    project_dest_dir = config.PROJECT_FOLDER / project_source_dir.name
    copy_tree(project_source_dir.as_posix(), project_dest_dir.as_posix())
    previous_project_folder = config.PROJECT_FOLDER
    config.PROJECT_FOLDER = project_dest_dir
    yield project_dest_dir
    config.PROJECT_FOLDER = previous_project_folder


@pytest.fixture
def project(project_folder):
    previous_project = ape.project
    project = Project(project_folder)
    ape.project = project
    yield project
    ape.project = previous_project


@pytest.fixture
def runner(project_folder):
    previous_cwd = str(Path.cwd())
    os.chdir(str(project_folder))
    runner = CliRunner()
    yield runner
    os.chdir(previous_cwd)


@pytest.fixture(scope="session")
def ape_cli():
    from ape._cli import cli

    yield cli
