from tests.integration.cli.utils import run_once


@run_once
def test_cache_init_purge(ape_cli, runner):
    cmd = ("cache", "init", "--network", "ethereum:goerli")
    result = runner.invoke(ape_cli, cmd)
    assert result.output == "SUCCESS: Caching database initialized for ethereum:goerli.\n"
    result = runner.invoke(ape_cli, ("cache", "purge", "--network", "ethereum:goerli"))
    assert result.output == "SUCCESS: Caching database purged for ethereum:goerli.\n"
