from contextlib import contextmanager
from importlib import import_module
from pathlib import Path
from shutil import copytree
from typing import Dict, List, Optional

import pytest

from ape.managers.config import CONFIG_FILE_NAME
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


@pytest.fixture(autouse=True)
def project_dir_map(project_folder):
    """
    Ensure only copying projects once to prevent `TooManyOpenFilesError`.
    """

    class ProjectDirCache:
        project_map: Dict[str, Path] = {}

        def load(self, name: str) -> Path:
            if name in self.project_map:
                # Already copied.
                return self.project_map[name]

            project_source_dir = __projects_directory__ / name
            project_dest_dir = project_folder / project_source_dir.name
            project_dest_dir.parent.mkdir(exist_ok=True, parents=True)

            if not project_dest_dir.is_dir():
                copytree(str(project_source_dir), str(project_dest_dir))

            self.project_map[name] = project_dest_dir
            return self.project_map[name]

    return ProjectDirCache()


@pytest.fixture(autouse=True, params=__project_names__)
def project(request, config, project_dir_map):
    project_dir = project_dir_map.load(request.param)
    with config.using_project(project_dir) as project:
        yield project


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
    cache_file = project.local_project.manifest_cachefile
    if cache_file.is_file():
        cache_file.unlink()

    project.local_project._cached_manifest = None

    yield

    if cache_file.is_file():
        cache_file.unlink()

    project.local_project._cached_manifest = None


@pytest.fixture
def switch_config(config):
    """
    A config-context switcher for Integration tests.
    It will change the contents of the active project's config file,
    reload it, yield, and change it back. Useful for testing different
    config scenarios without having to create entire new projects.
    """

    def replace_config(config_file, new_content: str):
        if config_file.is_file():
            config_file.unlink()

        config_file.touch()
        config_file.write_text(new_content)

    @contextmanager
    def switch(project, new_content: str):
        config_file = project.path / CONFIG_FILE_NAME
        original = config_file.read_text() if config_file.is_file() else None

        try:
            replace_config(config_file, new_content)
            config.load(force_reload=True)
            yield
        finally:
            if original:
                replace_config(config_file, original)
            elif config_file.is_file():
                # Delete created config.
                config_file.unlink()

        # Reload back
        config.load(force_reload=True)

    return switch


@pytest.fixture(scope="session")
def ape_plugins_runner():
    """
    Use subprocess runner so can manipulate site packages and see results.
    """

    class PluginSubprocessRunner(ApeSubprocessRunner):
        def __init__(self):
            super().__init__(["plugins"])

        def invoke_list(self, arguments: Optional[List] = None):
            arguments = arguments or []
            result = self.invoke(["list", *arguments])
            assert result.exit_code == 0, result.output
            return ListResult.parse_output(result.output)

    return PluginSubprocessRunner()
