import os
from distutils.dir_util import copy_tree
from importlib import import_module
from pathlib import Path

import pytest
from click.testing import CliRunner

import ape
from ape import Project

from .utils import NodeId, project_names, project_skipper, projects_directory


class IntegrationTestModule:
    """
    A test module in 'tests.integration.cli'.
    """

    def __init__(self, path: Path):
        self._path = path
        module = import_module(f"tests.integration.cli.{path.stem}")
        test_methods = [getattr(module, t) for t in dir(module) if t.startswith("test_")]
        self.tests = [NodeId(t) for t in test_methods]

    def __iter__(self):
        return iter(self.tests)

    @property
    def name(self) -> str:
        """
        The name of the module.
        """
        return self._path.stem


# Loads the actual test modules / methods
integration_tests = [
    IntegrationTestModule(p)
    for p in Path(__file__).parent.iterdir()
    if p.suffix == ".py" and p.name.startswith("test_")
]


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(session, config, items):
    """
    Filter out tests marked to be skipped using ``skip_projects``
    and the ``skip_projects_except`` decorators.
    """
    modified_items = []
    for item in items:
        item_name_parts = item.name.split("[")
        item_name_parts = [p.strip("[]") for p in item_name_parts]

        module_full_name = item.module.__name__
        module_name = module_full_name.split(".")[-1]
        test_name = item_name_parts[0]

        # Handle if a parametrized test is on-top
        # of the project's parametrization.
        project_name = item_name_parts[-1]
        for proj_name in project_skipper:

            # Example: 'test_foo[project-name-fuzz-0]' matches 'project-name'
            if project_name.startswith(proj_name):
                project_name = proj_name
                break

        is_cli_integration_test = (
            len(item_name_parts) == 2 and "integration.cli" in module_full_name
        )

        if not is_cli_integration_test or not project_skipper.do_skip(
            project_name, module_name, test_name
        ):
            modified_items.append(item)

    items[:] = modified_items


@pytest.fixture(params=project_names)
def project_folder(request, config):
    project_source_dir = projects_directory / request.param
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


def assert_failure(result, expected_output):
    assert result.exit_code == 1
    assert result.exception is not None
    assert "ERROR" in result.output
    assert expected_output in result.output


@pytest.fixture
def clean_cache(project):
    """
    Use this fixture to ensure a project
    does not have a cached compilation.
    """
    cache_file = project.manifest_cachefile
    if cache_file.exists():
        cache_file.unlink()

    yield

    if cache_file.exists():
        cache_file.unlink()
