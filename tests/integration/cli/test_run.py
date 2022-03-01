from .utils import skip_projects_except

BAD_COMMAND = "not-a-name"


@skip_projects_except(["script"])
def test_run_unknown_script(ape_cli, runner, project):
    result = runner.invoke(ape_cli, ["run", BAD_COMMAND])
    assert result.exit_code == 2
    assert f"No such command '{BAD_COMMAND}'." in result.output


def test_run(ape_cli, runner, project):
    for script_file in project.scripts_folder.glob("*.py"):
        if script_file.stem == "__init__":
            continue

        result = runner.invoke(ape_cli, ["run", script_file.stem])
        assert result.exit_code == 0, result.output

        assert "Super secret script output" in result.output
