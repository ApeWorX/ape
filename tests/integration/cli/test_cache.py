def test_cache_init_purge(ape_cli, runner):
    result = runner.invoke(ape_cli, ["cache", "init", "--network", "ethereum:rinkeby"])
    assert result.output == "SUCCESS: Caching database initialized for ethereum:rinkeby.\n"
    result = runner.invoke(ape_cli, ["cache", "purge", "--network", "ethereum:rinkeby"])
    assert result.output == "SUCCESS: Caching database purged for ethereum:rinkeby.\n"
