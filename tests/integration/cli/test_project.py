from .utils import skip_projects_except


@skip_projects_except(["with-dependencies"])
def test_get_project_without_contracts_path(project):
    project_path = project.path / "default"
    project = project.get_project(project_path)
    assert project.contracts_folder == project_path / "contracts"


@skip_projects_except(["with-dependencies"])
def test_get_project_with_contracts_path(project):
    project_path = project.path / "renamed_contracts_folder"
    project = project.get_project(project_path, project_path / "sources")
    assert project.contracts_folder != project_path / "contracts"
    assert project.contracts_folder == project_path / "sources"
