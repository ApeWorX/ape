from pathlib import Path

import pytest

from tests.conftest import ApeSubprocessRunner
from tests.integration.cli.utils import github_xfail, run_once, skip_projects_except

EXPECTED_FAIL_MESSAGE = "Unknown package '{}'."


@pytest.fixture
def pm_runner(config):
    class PMSubprocessRunner(ApeSubprocessRunner):
        def __init__(self):
            super().__init__(("pm",), data_folder=config.DATA_FOLDER)

    return PMSubprocessRunner()


@run_once
def test_install_path_not_exists(ape_cli, runner):
    path = "path/to/nowhere"
    result = runner.invoke(ape_cli, ("pm", "install", path))
    assert result.exit_code != 0, result.output
    assert EXPECTED_FAIL_MESSAGE.format(path) in result.output


@run_once
def test_install_path_to_local_package(ape_cli, runner, project):
    project_name = "with-contracts"
    path = Path(__file__).parent / "projects" / project_name
    name = path.stem
    result = runner.invoke(ape_cli, ("pm", "install", path.as_posix(), "--name", project_name))
    assert result.exit_code == 0, result.output
    assert f"Package '{path.as_posix()}' installed."

    # Ensure was installed correctly.
    assert (project.dependencies.packages_cache.projects_folder / name).is_dir()


@run_once
def test_install_path_to_local_config_file(ape_cli, runner):
    project = "with-contracts"
    path = Path(__file__).parent / "projects" / project / "ape-config.yaml"
    arguments = ("pm", "install", path.as_posix(), "--name", project)
    result = runner.invoke(ape_cli, arguments, catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert f"Package '{path.parent.as_posix()}' installed."


@skip_projects_except("test", "with-contracts")
def test_install_local_project_dependencies(ape_cli, runner):
    result = runner.invoke(ape_cli, ("pm", "install"))
    assert result.exit_code == 0
    assert "All project packages installed." in result.output


@run_once
def test_install_force(ape_cli, runner):
    result = runner.invoke(ape_cli, ("pm", "install", "--force"))
    assert result.exit_code == 0
    assert "All project packages installed." in result.output


@github_xfail()
def test_install_github_dependency_with_version(ape_cli, runner):
    result = runner.invoke(
        ape_cli,
        (
            "pm",
            "install",
            "gh:OpenZeppelin/openzeppelin-contracts",
            "--name",
            "OpenZeppelin",
            "--version",
            "4.6.0",
        ),
    )
    assert result.exit_code == 0, result.output
    assert "Package 'OpenZeppelin@4.6.0' installed."


@github_xfail()
def test_install_github_dependency_with_ref(ape_cli, runner):
    result = runner.invoke(
        ape_cli,
        (
            "pm",
            "install",
            "gh:OpenZeppelin/openzeppelin-contracts",
            "--name",
            "OpenZeppelin",
            "--ref",
            "master",
        ),
    )
    assert result.exit_code == 0, result.output
    assert "Package 'OpenZeppelin@master' installed."


@run_once
def test_install_config_override(runner, ape_cli):
    result = runner.invoke(
        ape_cli, ("pm", "install", "--config-override", '{"contracts_folder": "contracts}')
    )
    assert result.exit_code == 0, result.output
    assert "All project packages installed." in result.output


@run_once
def test_compile_package_not_exists(pm_runner, project):
    pm_runner.project = project
    name = "NOT_EXISTS"
    result = pm_runner.invoke(("compile", name))
    expected = f"Dependency '{name}' unknown. Is it installed?"
    assert result.exit_code != 0, result.output
    assert expected in result.output


@skip_projects_except("with-contracts", "with-dependencies")
def test_compile(pm_runner, project):
    pm_runner.project = project
    result = pm_runner.invoke(("compile", "--force"))
    output = result.output or str(result._completed_process.stderr)
    assert result.exit_code == 0, output

    if project.path.as_posix().endswith("with-contracts"):
        assert "Package 'foodep@local' compiled." in output, output
    else:
        # Tests against a bug where we couldn't have hyphens in
        # dependency project contracts.
        assert "contracts/hyphen-DependencyContract.json" in output, output


@skip_projects_except("with-contracts")
def test_compile_dependency(pm_runner, project):
    pm_runner.project = project
    name = "foodep"
    result = pm_runner.invoke(("compile", name, "--force"))
    assert result.exit_code == 0, result.output
    assert f"Package '{name}@local' compiled." in result.output


@skip_projects_except("only-dependencies")
def test_uninstall(pm_runner, project):
    pm_runner.project = project
    package_name = "dependency-in-project-only"

    # Install packages
    pm_runner.invoke(("install", ".", "--force"))

    result = pm_runner.invoke(("uninstall", package_name, "--yes"))
    expected_message = f"Uninstalled '{package_name}=local'."
    assert result.exit_code == 0, result.output or result._completed_process.stderr
    assert expected_message in result.output or result._completed_process.stderr


@skip_projects_except("only-dependencies")
def test_uninstall_not_exists(pm_runner, project):
    pm_runner.project = project
    package_name = "_this_does_not_exist_"
    result = pm_runner.invoke(("uninstall", package_name, "--yes"))
    expected_message = f"ERROR: Package(s) '{package_name}' not installed."
    assert result.exit_code != 0, result.output or result._completed_process.stderr
    assert expected_message in result.output


@skip_projects_except("only-dependencies")
def test_uninstall_specific_version(pm_runner, project):
    pm_runner.project = project
    package_name = "dependency-in-project-only"
    version = "local"

    # Install packages
    pm_runner.invoke(("install", ".", "--force"))

    result = pm_runner.invoke(("uninstall", package_name, version, "--yes"))
    expected_message = f"Uninstalled '{package_name}=local'."
    assert result.exit_code == 0, result.output
    assert expected_message in result.output


@skip_projects_except("only-dependencies")
def test_uninstall_all_versions(pm_runner, project):
    pm_runner.project = project

    # Install packages
    pm_runner.invoke(("install", ".", "--force"))

    package_name = "dependency-in-project-only"
    result = pm_runner.invoke(("uninstall", package_name, "--yes"))
    expected_message = f"Uninstalled '{package_name}=local'."
    assert result.exit_code == 0, result.output
    assert expected_message in result.output


@skip_projects_except("only-dependencies")
def test_uninstall_invalid_version(pm_runner, project):
    pm_runner.project = project
    package_name = "dependency-in-project-only"

    # Install packages
    pm_runner.invoke(("install", ".", "--force"))

    # Ensure was installed correctly.
    assert package_name in project.dependencies
    assert (project.dependencies.packages_cache.projects_folder / package_name).is_dir()

    invalid_version = "0.0.0"
    result = pm_runner.invoke(("uninstall", package_name, invalid_version, "--yes"))

    expected_message = f"Dependency '{package_name}' with version '{invalid_version}' not found"
    assert expected_message in result.output


@skip_projects_except("only-dependencies")
def test_list(pm_runner, project):
    pm_runner.project = project
    package_name = "dependency-in-project-only"
    result = pm_runner.invoke(("list",))
    assert result.exit_code == 0, result.output
    assert package_name in result.output
