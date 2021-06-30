BAD_COMMAND = "not-a-name"


def test_run(ape_cli, runner, project):
    result = runner.invoke(ape_cli, ["run"])
    assert result.exit_code == 1
    assert "Must provide at least one script name or path" in result.output

    result = runner.invoke(ape_cli, ["run", BAD_COMMAND])
    assert result.exit_code == 1
    if not (project.path / "scripts").exists():
        assert "No `scripts/` directory detected to run script" in result.output

    else:
        assert f"No script named '{BAD_COMMAND}' detected in scripts folder" in result.output

    for script_file in (project.path / "scripts").glob("*.py"):
        result = runner.invoke(ape_cli, ["run", script_file.stem])
        assert result.exit_code == 0
