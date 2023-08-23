from pathlib import Path

from tests.integration.cli.utils import github_xfail, run_once, skip_projects_except

EXPECTED_FAIL_MESSAGE = "Unknown package '{}'."


@run_once
def test_install_path_not_exists(ape_cli, runner):
    path = "path/to/nowhere"
    result = runner.invoke(ape_cli, ["pm", "install", path])
    assert result.exit_code != 0
    assert EXPECTED_FAIL_MESSAGE.format(path) in result.output


@run_once
def test_install_path_to_local_package(ape_cli, runner):
    project = "with-contracts"
    path = Path(__file__).parent / "projects" / project
    result = runner.invoke(ape_cli, ["pm", "install", path.as_posix(), "--name", project])
    assert result.exit_code == 0, result.output
    assert f"Package '{path.as_posix()}' installed."


@run_once
def test_install_path_to_local_config_file(ape_cli, runner):
    project = "with-contracts"
    path = Path(__file__).parent / "projects" / project / "ape-config.yaml"
    result = runner.invoke(ape_cli, ["pm", "install", path.as_posix(), "--name", project])
    assert result.exit_code == 0
    assert f"Package '{path.parent.as_posix()}' installed."


@skip_projects_except("test", "with-contracts")
def test_install_local_project_dependencies(ape_cli, runner):
    result = runner.invoke(ape_cli, ["pm", "install"])
    assert result.exit_code == 0
    assert "All project packages installed." in result.output


@run_once
def test_install_force(ape_cli, runner):
    result = runner.invoke(ape_cli, ["pm", "install", "--force"])
    assert result.exit_code == 0
    assert "All project packages installed." in result.output


@github_xfail()
def test_install_github_dependency_with_version(ape_cli, runner):
    result = runner.invoke(
        ape_cli,
        [
            "pm",
            "install",
            "gh:OpenZeppelin/openzeppelin-contracts",
            "--name",
            "OpenZeppelin",
            "--version",
            "4.6.0",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Package 'OpenZeppelin@4.6.0' installed."


@github_xfail()
def test_install_github_dependency_with_ref(ape_cli, runner):
    result = runner.invoke(
        ape_cli,
        [
            "pm",
            "install",
            "gh:OpenZeppelin/openzeppelin-contracts",
            "--name",
            "OpenZeppelin",
            "--ref",
            "master",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Package 'OpenZeppelin@master' installed."


@run_once
def test_compile_package_not_exists(ape_cli, runner):
    name = "NOT_EXISTS"
    result = runner.invoke(ape_cli, ["pm", "compile", name])
    expected = f"Dependency '{name}' unknown. Is it installed?"
    assert result.exit_code != 0
    assert expected in result.output


@skip_projects_except("with-contracts")
def test_compile(ape_cli, runner, project):
    result = runner.invoke(ape_cli, ["pm", "compile"])
    assert result.exit_code == 0, result.output
    assert "Package '__FooDep__' compiled." in result.output


@skip_projects_except("with-contracts")
def test_compile_dependency(ape_cli, runner, project):
    name = "__FooDep__"
    result = runner.invoke(ape_cli, ["pm", "compile", name])
    assert result.exit_code == 0, result.output
    assert f"Package '{name}' compiled." in result.output


# Remove tests
# 1. remove single package - ape pm remove Uniswap-core -y
# 2. remove single package with confirmation - ape pm remove Uniswap-core
#
# 3. prompt for option

# current testing Done
# `ape pm remove OpenZeppelin`
# Which versions of package 'OpenZeppelin' do you want to remove? ['v4.9.3', 'v4.9.1', 'v4.9.0'] (separate multiple versions with comma, or 'all'): v4.9.3
# Are you sure you want to remove version 'v4.9.3' of package 'OpenZeppelin'? [y/N]: y
# SUCCESS: Version 'v4.9.3' of package 'OpenZeppelin' removed.

# remove all versions of OpenZeppelin
# `ape pm remove OpenZeppelin -y`
# SUCCESS: Version 'v4.9.1' of package 'OpenZeppelin' removed.
# SUCCESS: Version 'v4.9.0' of package 'OpenZeppelin' removed.


@run_once
def test_remove_package_not_installed(ape_cli, runner):
    package_name = "UnknownPackage"
    result = runner.invoke(ape_cli, ["pm", "remove", package_name])
    expected_message = f"Package '{package_name}' is not installed."
    assert result.exit_code != 0
    assert expected_message in result.output


@run_once
def test_remove_specific_version(ape_cli, runner):
    package_name = "OpenZeppelin"
    version = "4.9.0"
    runner.invoke(
        ape_cli,
        [
            "pm",
            "install",
            "gh:OpenZeppelin/openzeppelin-contracts",
            "--name",
            "OpenZeppelin",
            "--version",
            "4.9.0",
        ],
    )
    result = runner.invoke(ape_cli, ["pm", "remove", package_name, version])
    expected_message = f"Version '{version}' of package '{package_name}' removed."
    assert result.exit_code == 0
    assert expected_message in result.output


@run_once
def test_remove_all_versions(ape_cli, runner):
    package_name = "OpenZeppelin"
    result = runner.invoke(ape_cli, ["pm", "remove", package_name, "--all"], input="y\n")
    expected_message = f"All versions of package '{package_name}' removed."
    assert result.exit_code == 0
    assert expected_message in result.output


@run_once
def test_remove_all_versions_with_y(ape_cli, runner):
    package_name = "OpenZeppelin"
    result = runner.invoke(ape_cli, ["pm", "remove", package_name, "--all", "-y"])
    expected_message = f"All versions of package '{package_name}' removed."
    assert result.exit_code == 0
    assert expected_message in result.output


@run_once
def test_remove_specific_version_with_y(ape_cli, runner):
    package_name = "OpenZeppelin"
    version = "4.9.3"
    result = runner.invoke(ape_cli, ["pm", "remove", package_name, version, "-y"])
    expected_message = f"Version '{version}' of package '{package_name}' removed."
    assert result.exit_code == 0
    assert expected_message in result.output


@run_once
def test_remove_cancel(ape_cli, runner):
    package_name = "OpenZeppelin"
    version = "4.9.0"
    result = runner.invoke(ape_cli, ["pm", "remove", package_name, version], input="n\n")
    assert result.exit_code == 0
    assert "Removal of version cancelled." in result.output


@run_once
def test_remove_invalid_version(ape_cli, runner):
    package_name = "OpenZeppelin"
    invalid_version = "4.9.5"
    result = runner.invoke(ape_cli, ["pm", "remove", package_name, invalid_version])
    expected_message = f"Version '{invalid_version}' of package '{package_name}' is not installed."
    assert result.exit_code != 0
    assert expected_message in result.output
