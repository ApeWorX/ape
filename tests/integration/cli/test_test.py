def test_test(ape_cli, runner, project):
    if not (project.path / "tests").exists():
        return  # Nothing to do for these tests

    result = runner.invoke(ape_cli, ["test"])
    assert result.exit_code == 0, result.output
