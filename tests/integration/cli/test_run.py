from .utils import skip_projects_except

BAD_COMMAND = "not-a-name"


@skip_projects_except(["script"])
def test_run_unknown_script(ape_cli, runner, project):
    result = runner.invoke(ape_cli, ["run", BAD_COMMAND])
    assert result.exit_code == 2
    assert f"No such command '{BAD_COMMAND}'." in result.output


def test_run(ape_cli, runner, project):
    result = runner.invoke(ape_cli, ["run"])
    assert result.exit_code == 0, result.output
    # By default, no commands are run
    assert "Super secret script output" not in result.output

    scripts = [s for s in project.scripts_folder.glob("*.py") if not s.name.startswith("error")]
    for script_file in scripts:
        result = runner.invoke(ape_cli, ["run", script_file.stem])
        assert result.exit_code == 0, result.output
        runner.invoke(ape_cli, ["run", "--interactive"], input="exit\n")
        assert result.exit_code == 0, result.output

        if script_file.stem.startswith("_"):
            assert "Super secret script output" not in result.output

        else:
            assert "Super secret script output" in result.output


def test_run_when_script_errors(ape_cli, runner, project):
    scripts = [s for s in project.scripts_folder.glob("*.py") if s.name.startswith("error")]
    for script_file in scripts:
        result = runner.invoke(ape_cli, ["run", script_file.stem])
        assert result.exit_code != 0, result.output
        runner.invoke(ape_cli, ["run", "--interactive"], input="exit\n")
        assert result.exit_code != 0, result.output
        assert str(result.exception) == "Expected exception"


def test_run_interactive(ape_cli, runner, project):
    result = runner.invoke(ape_cli, ["run", "--interactive"], input="exit\n")
    assert result.exit_code == 0, result.output
