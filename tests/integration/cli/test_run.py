def test_run(ape_cli, runner, project):
    if not (project.path / "scripts").exists():
        result = runner.invoke(ape_cli, ["run"])
        assert result.exit_code == 0
        assert "WARNING: No `scripts/` directory detected" in result.output
        return  # Nothing else to test for this project

    result = runner.invoke(ape_cli, ["run"])
    assert result.exit_code == 1

    for script_file in (project.path / "scripts").glob("*.py"):
        result = runner.invoke(ape_cli, ["run", script_file.stem])
        assert result.exit_code == 0
