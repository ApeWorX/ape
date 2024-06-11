from importlib import import_module
from pathlib import Path
from shutil import copytree
from typing import Optional

import pytest

from ape import Project
from tests.conftest import ApeSubprocessRunner

from .test_plugins import ListResult
from .utils import NodeId, __project_names__, __projects_directory__, project_skipper


class IntegrationTestModule:
    """
    A test module in 'tests.integration.cli'.
    """

    def __init__(self, path: Path):
        self._path = path
        module = import_module(f"tests.integration.cli.{path.stem}")
        test_methods = [
            getattr(module, t)
            for t in dir(module)
            if t.startswith("test_") and hasattr(t, "__name__") and hasattr(t, "__module__")
        ]
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

        module_full_name = getattr(item.module, "__name__", None)
        if not module_full_name:
            continue

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


@pytest.fixture(autouse=True, scope="session")
def project_dir_map():
    """
    Ensure only copying projects once to prevent `TooManyOpenFilesError`.
    """

    class ProjectDirCache:
        project_map: dict[str, Path] = {}

        def load(self, name: str) -> Path:
            base_path = Path(__file__).parent / "projects"
            if name in self.project_map:
                res = self.project_map[name]
                if res.is_dir():
                    # Already copied and still exists!
                    return res

            # Either re-copy or copy for the first time.
            project_source_dir = __projects_directory__ / name
            project_dest_dir = base_path / project_source_dir.name
            project_dest_dir.parent.mkdir(exist_ok=True, parents=True)

            if not project_dest_dir.is_dir():
                copytree(project_source_dir, project_dest_dir)

            self.project_map[name] = project_dest_dir
            return self.project_map[name]

    return ProjectDirCache()


@pytest.fixture(autouse=True, params=__project_names__)
def integ_project(request, project_dir_map):
    project_dir = project_dir_map.load(request.param)
    if not project_dir.is_dir():
        # Should not happen because of logic in fixture,
        # but just in case!
        pytest.fail("Setup failed - project dir not exists.")

    root_project = Project(project_dir)
    # Using tmp project so no .build folder get kept around.
    with root_project.isolate_in_tempdir(name=request.param) as tmp_project:
        assert tmp_project.path.is_dir(), "Setup failed - tmp-project dir not exists"
        yield tmp_project


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
    project.clean()
    yield
    project.clean()


@pytest.fixture(scope="session")
def ape_plugins_runner(config):
    """
    Use subprocess runner so can manipulate site packages and see results.
    """

    class PluginSubprocessRunner(ApeSubprocessRunner):
        def __init__(self):
            super().__init__("plugins", data_folder=config.DATA_FOLDER)

        def invoke_list(self, arguments: Optional[list] = None):
            arguments = arguments or []
            result = self.invoke("list", *arguments)
            assert result.exit_code == 0, result.output
            return ListResult.parse_output(result.output)

    return PluginSubprocessRunner()
