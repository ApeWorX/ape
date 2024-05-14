from collections.abc import Callable
from pathlib import Path

import pytest

__projects_directory__ = Path(__file__).parent / "projects"
__project_names__ = [
    p.stem for p in __projects_directory__.iterdir() if p.is_dir() and not p.stem.startswith(".")
]


def assert_failure(result, expected_output):
    assert result.exit_code == 1
    assert result.exception is not None
    assert "ERROR" in result.output
    assert expected_output in result.output


class NodeId:
    """
    A class that extracts a callable test's name and module name.
    """

    def __init__(self, test_method: Callable):
        self.module_full_name = test_method.__module__
        self.name = test_method.__name__

    @property
    def module_name(self) -> str:
        return self.module_full_name.split(".")[-1]

    @property
    def node_id(self) -> str:
        return f"{self.module_name}.{self.name}"


class ProjectSkipper:
    """
    A class that contains stateful information about
    which projects to skip tests for.
    """

    def __init__(self):
        self.projects: dict[str, dict] = {n: {} for n in __project_names__}

    def __iter__(self):
        return iter(self.projects)

    def do_skip(self, project: str, module: str, test: str) -> bool:
        """
        Returns ``True`` if a test has been marked to be
        skipped for the given project using the ``skip_project`` or
        ``skip_project_except`` decorators.
        """
        if project not in self.projects:
            # Not a project-based integration test
            return False

        result = test in self.projects[project].get(module, [])
        return result

    def _raise_if_not_exists(self, project_name: str, node_id: str):
        if project_name not in self.projects:
            raise pytest.Collector.CollectError(
                f"Project '{project_name}' does not exist (test={node_id}."
            )

    def skip_projects(self, method: Callable, *projects: str):
        """
        Call this method to record a 'skip'.
        The ``skip_project`` decorator calls this method
        on the test method they are wrapped around.
        """
        assert hasattr(method, "__name__") and hasattr(method, "__module__")
        node = NodeId(method)
        for project in projects:
            self._raise_if_not_exists(project, node.node_id)
            if node.module_name not in self.projects[project]:
                self.projects[project][node.module_name] = set()

            self.projects[project][node.module_name].add(node.name)

    def skip_projects_except(self, method: Callable, *projects: str):
        """
        Call this method to record 'skip's for each project that is not
        in the given list. The ``skip_project_except`` decorator calls
        this method on the test method they are wrapped around.
        """
        assert hasattr(method, "__name__") and hasattr(method, "__module__")
        node = NodeId(method)

        # Verify projects to run for exist
        for proj in projects:
            self._raise_if_not_exists(proj, node.node_id)

        filtered_projects = [p for p in self.projects if p not in projects]
        self.skip_projects(method, *filtered_projects)


project_skipper = ProjectSkipper()


def skip_projects(*names: str):
    """
    Use this decorator to cause a CLI integration test
    not to run for the given projects.
    """

    def decorator(f):
        project_skipper.skip_projects(f, *names)
        return f

    return decorator


def skip_projects_except(*names: str):
    """
    Use this decorator to cause a CLI integration test
    to only run for the given projects.
    """

    def decorator(f):
        project_skipper.skip_projects_except(f, *names)
        return f

    return decorator


run_once = skip_projects_except("test")
"""
For times when the CLI integration test is unlikely to be
affected by project structure.
"""


def github_xfail():
    """
    Expects failures because of GitHib rate limiting
    """

    def wrapper(f):
        f = pytest.mark.xfail(
            strict=False, reason="GitHub rate limiting issues or plugin install issues"
        )(f)
        f = run_once(f)
        return f

    return wrapper
