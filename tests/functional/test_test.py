import pytest

from ape.exceptions import ConfigError
from ape.pytest.runners import PytestApeRunner
from ape_test import ApeTestConfig


class TestApeTestConfig:
    def test_balance_set_from_currency_str(self):
        curr_val = "10 Eth"
        data = {"balance": curr_val}
        cfg = ApeTestConfig.model_validate(data)
        actual = cfg.balance
        expected = 10_000_000_000_000_000_000  # 10 ETH in WEI
        assert actual == expected


def test_connect_to_mainnet_by_default(mocker):
    """
    Tests the condition where mainnet is configured as the default network
    and no --network option is passed. It should avoid running the tests
    to be safe.
    """

    cfg = mocker.MagicMock()
    cfg.network = "ethereum:mainnet:node"
    runner = PytestApeRunner(cfg, mocker.MagicMock(), mocker.MagicMock(), mocker.MagicMock())

    expected = (
        "Default network is mainnet; unable to run tests on mainnet. "
        "Please specify the network using the `--network` flag or "
        "configure a different default network."
    )
    with pytest.raises(ConfigError, match=expected):
        runner._connect()
