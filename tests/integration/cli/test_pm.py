from pathlib import Path

from tests.integration.cli.utils import github_xfail, run_once, skip_projects_except

EXPECTED_FAIL_MESSAGE = "Unknown package '{}'."


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
    assert (project.dependency_manager.DATA_FOLDER / "packages" / name).is_dir()


@run_once
def test_install_path_to_local_config_file(ape_cli, runner):
    project = "with-contracts"
    path = Path(__file__).parent / "projects" / project / "ape-config.yaml"
    result = runner.invoke(
        ape_cli, ("pm", "install", path.as_posix(), "--name", project), catch_exceptions=False
    )
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


@skip_projects_except("with-contracts")
def test_install_config_override(ape_cli, runner, project):
    config_override = '{"contracts_folder": "src"}'
    dep_path = project.path / "dep"
    name = "foodep2"
    result = runner.invoke(
        ape_cli,
        (
            "pm",
            "install",
            dep_path.as_posix(),
            "--name",
            name,
            "--config-override",
            config_override,
            "--force",
        ),
    )
    assert (
        f"No source files found in dependency '{name}'. "
        "Try adjusting its config using `config_override`"
    ) in result.output


@run_once
def test_compile_package_not_exists(ape_cli, runner):
    name = "NOT_EXISTS"
    result = runner.invoke(ape_cli, ("pm", "compile", name))
    expected = f"Dependency '{name}' unknown. Is it installed?"
    assert result.exit_code != 0, result.output
    assert expected in result.output


@skip_projects_except("with-contracts", "with-dependencies")
def test_compile(ape_cli, runner, project):
    result = runner.invoke(ape_cli, ("pm", "compile", "--force"))
    assert result.exit_code == 0, result.output

    if project.path.as_posix().endswith("with-contracts"):
        assert "Package 'foodep' compiled." in result.output
    else:
        # Tests against a bug where we couldn't have hyphens in
        # dependency project contracts.
        assert "Compiling 'hyphen-DependencyContract.json'" in result.output


@skip_projects_except("with-contracts")
def test_compile_config_override(ape_cli, runner, project):
    name = "foodep"
    result = runner.invoke(
        ape_cli,
        ("pm", "compile", name, "--force", "--config-override", '{"contracts_folder": "src"}'),
    )
    assert result.exit_code == 0, result.output
    assert f"Package '{name}' compiled." in result.output


@skip_projects_except("only-dependencies")
def test_remove(ape_cli, runner, project):
    package_name = "dependency-in-project-only"

    # Install packages
    runner.invoke(ape_cli, ("pm", "install", ".", "--force"))

    result = runner.invoke(ape_cli, ("pm", "remove", package_name), input="y\n")
    expected_message = f"Version 'local' of package '{package_name}' removed."
    assert result.exit_code == 0, result.output
    assert expected_message in result.output


@skip_projects_except("only-dependencies")
def test_remove_not_exists(ape_cli, runner, project):
    package_name = "_this_does_not_exist_"
    result = runner.invoke(ape_cli, ("pm", "remove", package_name))
    expected_message = f"ERROR: Package '{package_name}' is not installed."
    assert result.exit_code != 0, result.output
    assert expected_message in result.output


@skip_projects_except("only-dependencies")
def test_remove_specific_version(ape_cli, runner, project):
    package_name = "dependency-in-project-only"
    version = "local"

    # Install packages
    runner.invoke(ape_cli, ("pm", "install", ".", "--force"))

    result = runner.invoke(ape_cli, ("pm", "remove", package_name), input="y\n")
    expected_message = f"Version '{version}' of package '{package_name}' removed."
    assert result.exit_code == 0, result.output
    assert expected_message in result.output


@skip_projects_except("only-dependencies")
def test_remove_all_versions_with_y(ape_cli, runner):
    # Install packages
    runner.invoke(ape_cli, ("pm", "install", ".", "--force"))

    package_name = "dependency-in-project-only"
    result = runner.invoke(ape_cli, ("pm", "remove", package_name, "-y"))
    expected_message = f"SUCCESS: Version 'local' of package '{package_name}' removed."
    assert result.exit_code == 0, result.output
    assert expected_message in result.output


@skip_projects_except("only-dependencies")
def test_remove_specific_version_with_y(ape_cli, runner):
    # Install packages
    runner.invoke(ape_cli, ("pm", "install", ".", "--force"))

    package_name = "dependency-in-project-only"
    version = "local"
    result = runner.invoke(ape_cli, ["pm", "remove", package_name, version, "-y"])
    expected_message = f"Version '{version}' of package '{package_name}' removed."
    assert result.exit_code == 0, result.output
    assert expected_message in result.output


@skip_projects_except("only-dependencies")
def test_remove_cancel(ape_cli, runner):
    # Install packages
    runner.invoke(ape_cli, ["pm", "install", ".", "--force"])

    package_name = "dependency-in-project-only"
    version = "local"
    result = runner.invoke(ape_cli, ["pm", "remove", package_name, version], input="n\n")
    assert result.exit_code == 0, result.output
    expected_message = f"Version '{version}' of package '{package_name}' removed."
    assert expected_message not in result.output


@skip_projects_except("only-dependencies")
def test_remove_invalid_version(ape_cli, runner, project):
    package_name = "dependency-in-project-only"

    # Install packages
    runner.invoke(ape_cli, ["pm", "install", ".", "--force"])

    # Ensure was installed correctly.
    assert package_name in project.dependencies
    assert (project.dependency_manager.DATA_FOLDER / "packages" / package_name).is_dir()

    invalid_version = "0.0.0"
    result = runner.invoke(ape_cli, ["pm", "remove", package_name, invalid_version])

    expected_message = f"Version '{invalid_version}' of package '{package_name}' is not installed."
    assert expected_message in result.output


@skip_projects_except("only-dependencies")
def test_list(ape_cli, runner):
    package_name = "dependency-in-project-only"
    result = runner.invoke(ape_cli, ["pm", "list"])
    assert result.exit_code == 0, result.output
    assert package_name in result.output
