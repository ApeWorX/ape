import pytest

from ape.exceptions import ConfigError
from ape.pytest.plugin import _get_default_network
from ape_test import ApeTestConfig


class TestApeTestConfig:
    def test_balance_set_from_currency_str(self):
        curr_val = "10 Eth"
        data = {"balance": curr_val}
        cfg = ApeTestConfig.model_validate(data)
        actual = cfg.balance
        expected = 10_000_000_000_000_000_000  # 10 ETH in WEI
        assert actual == expected


def test_get_default_network(mocker):
    # NOTE: Using this weird test to avoid actually
    #  using mainnet in any test, even accidentally.
    mock_ecosystem = mocker.MagicMock()
    mock_mainnet = mocker.MagicMock()
    mock_mainnet.name = "mainnet"
    mock_ecosystem.default_network = mock_mainnet
    expected = (
        "Default network is mainnet; unable to run tests on mainnet. "
        "Please specify the network using the `--network` flag or "
        "configure a different default network."
    )
    with pytest.raises(ConfigError, match=expected):
        _get_default_network(mock_mainnet)
