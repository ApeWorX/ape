from pathlib import Path

from ape import Project


def test_can_access_contract():
    project_dir = Path(__file__).parent / "cli" / "projects" / "one-interface"
    project = Project(project_dir)
    assert project.Interface
