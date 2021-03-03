def test_invocation(ape_cli, runner):
    result = runner.invoke(ape_cli)
    assert result.exit_code == 0
