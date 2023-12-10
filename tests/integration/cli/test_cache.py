def test_cache_init_purge(ape_cli, runner, mock_sys_argv):
    cmd = ("cache", "init", "--network", "ethereum:goerli")
    mock_sys_argv.return_value = ["ape", *cmd]  # For --network option
    result = runner.invoke(ape_cli, cmd)
    assert result.output == "SUCCESS: Caching database initialized for ethereum:goerli.\n"
    result = runner.invoke(ape_cli, ["cache", "purge", "--network", "ethereum:goerli"])
    assert result.output == "SUCCESS: Caching database purged for ethereum:goerli.\n"
