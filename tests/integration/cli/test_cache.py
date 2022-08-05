def test_cache_init_fail(ape_cli, runner, networks):
    result = runner.invoke(ape_cli, ["cache", "init", "--network", ":rinkeby"])
    assert result.output == "ERROR: (ProviderError) No node found on 'http://localhost:8545'.\n"
