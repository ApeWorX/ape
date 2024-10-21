import shutil
from pathlib import Path

import pytest

from tests.conftest import ApeSubprocessRunner, skip_if_plugin_installed
from tests.integration.cli.utils import github_xfail, run_once, skip_projects_except

EXPECTED_FAIL_MESSAGE = "Unknown package '{}'."


@pytest.fixture
def pm_runner(config):
    class PMSubprocessRunner(ApeSubprocessRunner):
        def __init__(self):
            super().__init__("pm", data_folder=config.DATA_FOLDER)

    return PMSubprocessRunner()


@run_once
def test_install_path_not_exists(pm_runner):
    path = "path/to/nowhere"
    result = pm_runner.invoke("install", path)
    assert result.exit_code != 0, result.output
    assert EXPECTED_FAIL_MESSAGE.format(path) in result._completed_process.stderr


@run_once
def test_install_path_to_local_package(pm_runner, integ_project):
    project_name = "with-contracts"
    path = Path(__file__).parent / "projects" / project_name
    name = path.stem
    result = pm_runner.invoke("install", path.as_posix(), "--name", project_name)
    assert result.exit_code == 0, result.output
    assert f"Package '{path.as_posix()}' installed."

    # Ensure was installed correctly.
    assert integ_project.dependencies[name]["local"]


@run_once
def test_install_path_to_local_config_file(pm_runner):
    project = "with-contracts"
    path = Path(__file__).parent / "projects" / project / "pyproject.toml"
    arguments = ("install", path.as_posix(), "--name", project)
    result = pm_runner.invoke(*arguments)
    assert result.exit_code == 0, result.output
    assert "SUCCESS" in result.output
    assert "Package 'with-contracts@local' installed." in result.output


@skip_projects_except("test", "with-contracts")
def test_install_local_project_dependencies(pm_runner):
    result = pm_runner.invoke("install")
    assert result.exit_code == 0
    assert "All project packages installed." in result.output


@run_once
def test_install_force(pm_runner):
    result = pm_runner.invoke("install", "--force")
    assert result.exit_code == 0
    assert "All project packages installed." in result.output


@run_once
@github_xfail()
def test_install_github_dependency_with_version(pm_runner):
    result = pm_runner.invoke(
        "install",
        "gh:OpenZeppelin/openzeppelin-contracts",
        "--name",
        "openzeppelin",
        "--version",
        "4.6.0",
        timeout=300,
    )
    assert result.exit_code == 0, result.output
    assert "Package 'openzeppelin@4.6.0' installed."


@run_once
@github_xfail()
def test_install_github_dependency_with_ref(pm_runner):
    result = pm_runner.invoke(
        "install",
        "gh:OpenZeppelin/openzeppelin-contracts",
        "--name",
        "OpenZeppelin",
        "--ref",
        "master",
        timeout=300,
    )
    assert result.exit_code == 0, result.output
    assert "Package 'OpenZeppelin@master' installed."


@skip_projects_except("with-contracts")
def test_install_config_override(pm_runner, integ_project):
    actual_dep = Path(__file__).parent / "projects" / "with-contracts" / "dep"
    shutil.copytree(actual_dep, integ_project.path / "dep")
    config_override = '{"contracts_folder": "src"}'
    dep_path = integ_project.path / "dep"
    name = "foodep2"
    pm_runner.invoke(
        "install",
        dep_path.as_posix(),
        "--name",
        name,
        "--config-override",
        config_override,
        "--force",
    )
    actual = integ_project.dependencies["foodep2"]["local"].config.contracts_folder
    assert actual == "src"


@run_once
def test_compile_package_not_exists(pm_runner, integ_project):
    pm_runner.project = integ_project
    name = "NOT_EXISTS"
    result = pm_runner.invoke("compile", name)
    expected = f"Dependency '{name}' unknown. Is it installed?"
    assert result.exit_code != 0, result.output
    assert expected in result.output


@skip_projects_except("with-contracts", "with-dependencies")
def test_compile(pm_runner, integ_project):
    pm_runner.project = integ_project
    result = pm_runner.invoke("compile", "--force")
    output = result.output or str(result._completed_process.stderr)
    assert result.exit_code == 0, output

    if integ_project.path.as_posix().endswith("contracts"):
        assert "Package 'foodep@local' compiled." in output, output
    else:
        # Tests against a bug where we couldn't have hyphens in
        # dependency project contracts.
        assert "contracts/hyphen-DependencyContract.json" in output, output


@skip_projects_except("with-contracts")
def test_compile_config_override(pm_runner, integ_project):
    pm_runner.project = integ_project
    cmd = ("compile", "--force", "--config-override", '{"contracts_folder": "src"}')
    result = pm_runner.invoke(*cmd)
    output = result.output or str(result._completed_process.stderr)
    assert result.exit_code == 0, output


@skip_projects_except("with-contracts")
def test_compile_dependency(pm_runner, integ_project):
    pm_runner.project = integ_project
    name = "foodep"

    # Show staring from a clean slate.
    pm_runner.invoke("uninstall", name, "--yes")

    result = pm_runner.invoke("compile", name, "--force")
    assert result.exit_code == 0, result.output
    assert f"Package '{name}@local' compiled." in result.output

    # Show it can happen more than once. (no --force this time).
    result = pm_runner.invoke("compile", name)
    assert result.exit_code == 0, result.output
    assert f"Package '{name}@local' compiled." in result.output

    # Clean for next tests.
    pm_runner.invoke("uninstall", name, "--yes")


@skip_if_plugin_installed("vyper", "solidity")
@skip_projects_except("with-contracts")
def test_compile_missing_compiler_plugins(pm_runner, integ_project, compilers):
    pm_runner.project = integ_project
    name = "depwithunregisteredcontracts"

    # Stateful clean up (just in case?)
    pm_runner.invoke("uninstall", name, "--yes")

    result = pm_runner.invoke("compile", name, "--force")
    expected = (
        "Compiling dependency produced no contract types. "
        "Try installing 'ape-solidity' or 'ape-vyper'"
    )
    assert expected in result.output

    # Also show it happens when installing _all_.
    result = pm_runner.invoke("compile", ".", "--force")
    pm_runner.invoke("uninstall", name, "--yes")

    assert expected in result.output


@skip_projects_except("only-dependencies")
def test_uninstall(pm_runner, integ_project):
    pm_runner.project = integ_project
    package_name = "dependency-in-project-only"

    # Install packages
    pm_runner.invoke("install", ".", "--force")
    result = pm_runner.invoke("uninstall", package_name, "--yes")
    expected_message = f"Uninstalled '{package_name}=local'."
    assert result.exit_code == 0, result.output or result._completed_process.stderr
    assert expected_message in result.output or result._completed_process.stderr


@skip_projects_except("only-dependencies")
def test_uninstall_by_long_name(pm_runner, integ_project):
    pm_runner.project = integ_project
    package_name = "dependency-in-project-only"
    package_long_name = integ_project.dependencies.get_dependency(package_name, "local").package_id

    # Install packages
    pm_runner.invoke("install", ".", "--force")
    result = pm_runner.invoke("uninstall", package_long_name, "--yes")
    expected_message = f"Uninstalled '{package_name}=local'."
    assert result.exit_code == 0, result.output or result._completed_process.stderr
    assert expected_message in result.output or result._completed_process.stderr


@skip_projects_except("only-dependencies")
def test_uninstall_not_exists(pm_runner, integ_project):
    pm_runner.project = integ_project
    package_name = "_this_does_not_exist_"
    result = pm_runner.invoke("uninstall", package_name, "--yes")
    expected_message = f"Package(s) '{package_name}' not installed."
    assert result.exit_code != 0, result.output or result._completed_process.stderr
    assert "ERROR" in result.output
    assert expected_message in result.output


@skip_projects_except("only-dependencies")
def test_uninstall_specific_version(pm_runner, integ_project):
    pm_runner.project = integ_project
    package_name = "dependency-in-project-only"
    version = "local"

    # Install packages
    pm_runner.invoke("install", ".", "--force")
    result = pm_runner.invoke("uninstall", package_name, version, "--yes")
    expected_message = f"Uninstalled '{package_name}=local'."
    assert result.exit_code == 0, result.output
    assert expected_message in result.output


@skip_projects_except("only-dependencies")
def test_uninstall_all_versions(pm_runner, integ_project):
    pm_runner.project = integ_project
    # Install packages
    pm_runner.invoke("install", ".", "--force")
    package_name = "dependency-in-project-only"
    result = pm_runner.invoke("uninstall", package_name, "--yes")
    expected_message = f"Uninstalled '{package_name}=local'."
    assert result.exit_code == 0, result.output
    assert expected_message in result.output


@skip_projects_except("only-dependencies")
def test_uninstall_invalid_version(pm_runner, integ_project):
    pm_runner.project = integ_project
    package_name = "dependency-in-project-only"

    # Install packages
    pm_runner.invoke("install", ".", "--force")

    # Ensure was installed correctly.
    assert package_name in integ_project.dependencies
    assert integ_project.dependencies[package_name]["local"]

    invalid_version = "0.0.0"
    result = pm_runner.invoke("uninstall", package_name, invalid_version, "--yes")
    expected_message = f"Package(s) '{package_name}={invalid_version}' not installed."
    assert result.exit_code != 0, result.output

    assert "ERROR" in result.output
    assert expected_message in result.output


@skip_projects_except("only-dependencies")
def test_uninstall_cancel(pm_runner, integ_project):
    pm_runner.project = integ_project
    package_name = "dependency-in-project-only"
    version = "local"

    # Install packages
    pm_runner.invoke("install", ".", "--force")

    result = pm_runner.invoke("uninstall", package_name, version, input="n\n")
    assert result.exit_code == 0, result._completed_process.stderr
    expected_message = f"Version '{version}' of package '{package_name}' uninstalled."
    assert expected_message not in result.output


@skip_projects_except("only-dependencies")
def test_list(pm_runner, integ_project):
    pm_runner.project = integ_project
    package_name = "dependency-in-project-only"
    dependency = integ_project.dependencies.get_dependency(package_name, "local")

    # Ensure we are not installed.
    dependency.uninstall()

    result = pm_runner.invoke("list")
    assert result.exit_code == 0, result.output

    # NOTE: Not using f-str here so we can see the spacing.
    expected = """
NAME                        VERSION  INSTALLED  COMPILED
dependency-in-project-only  local    False      False
    """.strip()
    assert expected in result.output

    # Install and show it change.
    dependency = integ_project.dependencies.get_dependency(package_name, "local")
    dependency.install()

    expected = """
NAME                        VERSION  INSTALLED  COMPILED
dependency-in-project-only  local    True       False
    """.strip()
    result = pm_runner.invoke("list")
    assert result.exit_code == 0, result.output
    assert expected in result.output
