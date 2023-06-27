from pathlib import Path

from tests.integration.cli.utils import run_once, skip_projects_except

EXPECTED_FAIL_MESSAGE = (
    "'dependency' must be a path to an ape project or a value like 'name=version'"
)


@run_once
def test_install_path_not_exists(ape_cli, runner):
    path = "path/to/nowhere"
    result = runner.invoke(ape_cli, ["pm", "install", path])
    assert result.exit_code != 0
    assert EXPECTED_FAIL_MESSAGE in result.output


@run_once
def test_install_path_to_local_package(ape_cli, runner):
    path = Path(__file__).parent / "projects" / "with-contracts"
    result = runner.invoke(ape_cli, ["pm", "install", path.as_posix()])
    assert result.exit_code == 0
    assert f"Package '{path.as_posix()}' installed."


@run_once
def test_install_path_to_local_config_file(ape_cli, runner):
    path = Path(__file__).parent / "projects" / "with-contracts" / "ape-config.yaml"
    result = runner.invoke(ape_cli, ["pm", "install", path.as_posix()])
    assert result.exit_code == 0
    assert f"Package '{path.parent.as_posix()}' installed."


@run_once
def test_install_dependency_missing_version(ape_cli, runner):
    result = runner.invoke(ape_cli, ["pm", "install", "name"])
    assert result.exit_code != 0
    assert EXPECTED_FAIL_MESSAGE in result.output


@run_once
def test_install_dependency(ape_cli, runner):
    package = "OpenZeppelin=4.6.0"
    result = runner.invoke(
        ape_cli,
        ["pm", "install", package, "--github", "OpenZeppelin/openzeppelin-contracts"],
    )
    assert result.exit_code == 0, result.output
    assert f"Package '{package}' installed."


@run_once
def test_install_force(ape_cli, runner):
    result = runner.invoke(ape_cli, ["pm", "install", "name", "--force"])
    assert result.exit_code != 0
    assert EXPECTED_FAIL_MESSAGE in result.output


@run_once
def test_compile_package_not_exists(ape_cli, runner):
    name = "NOT_EXISTS"
    result = runner.invoke(ape_cli, ["pm", "compile", name])
    expected = f"Dependency '{name}' unknown. Is it installed?"
    assert result.exit_code != 0
    assert expected in result.output


@skip_projects_except("with-contracts")
def test_compile(ape_cli, runner, project):
    name = "__FooDep__"
    result = runner.invoke(ape_cli, ["pm", "compile", name])
    assert result.exit_code == 0, result.output
    assert f"Package '{name}' compiled." in result.output
