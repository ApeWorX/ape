from .utils import skip_projects

BAD_COMMAND = "not-a-name"


@skip_projects(["script", "geth"])
def test_run_no_scripts_dir(ape_cli, runner, project):
    result = runner.invoke(ape_cli, ["run", BAD_COMMAND])
    assert result.exit_code == 1, result.output
    assert "No 'scripts/' directory detected to run script" in result.output


@skip_projects(
    ["empty-config", "no-config", "one-interface", "unregistered-contracts", "test", "geth"]
)
def test_run(ape_cli, runner, project):
    result = runner.invoke(ape_cli, ["run"])
    assert result.exit_code == 1, result.output
    assert "Must provide at least one script name or path" in result.output

    result = runner.invoke(ape_cli, ["run", BAD_COMMAND])
    assert result.exit_code == 1
    assert f"No script named '{BAD_COMMAND}' detected in scripts folder" in result.output

    for script_file in (project.path / "scripts").glob("*.py"):
        if script_file.stem == "__init__":
            continue

        result = runner.invoke(ape_cli, ["run", script_file.stem])
        assert result.exit_code == 0, result.output
