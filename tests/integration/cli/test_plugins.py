def test_list_excludes_core_plugins(ape_cli, runner):
    result = runner.invoke(ape_cli, ["plugins", "list"])
    assert result.exit_code == 0, result.output
    assert "plugins" not in result.output, "plugins is not supposed to be in Installed Plugins"
    assert "console" not in result.output, "console is not supposed to be in Installed Plugins"
    assert "networks" not in result.output, "networks is not supposed to be in Installed Plugins"
