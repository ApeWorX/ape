from pathlib import Path

import pytest

from ape.exceptions import ConfigError
from ape.pytest.runners import PytestApeRunner
from ape_test import ApeTestConfig
from ape_test._watch import run_with_observer


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


def test_watch(mocker):
    mock_event_handler = mocker.MagicMock()
    event_handler_patch = mocker.patch("ape_test._watch._create_event_handler")
    event_handler_patch.return_value = mock_event_handler

    mock_observer = mocker.MagicMock()
    observer_patch = mocker.patch("ape_test._watch._create_observer")
    observer_patch.return_value = mock_observer

    run_subprocess_patch = mocker.patch("ape_test._watch.run_subprocess")
    run_main_loop_patch = mocker.patch("ape_test._watch._run_main_loop")
    run_main_loop_patch.side_effect = SystemExit  # Avoid infinite loop.

    # Only passing `-s` so we have an extra arg to test.
    with pytest.raises(SystemExit):
        run_with_observer((Path("contracts"),), 0.1, "-s")

    # The observer started, then the main runner exits, and the observer stops + joins.
    assert mock_observer.start.call_count == 1
    assert mock_observer.stop.call_count == 1
    assert mock_observer.join.call_count == 1

    # NOTE: We had a bug once where the args it received were not strings.
    #   (wasn't deconstructing), so this check is important.
    run_subprocess_patch.assert_called_once_with(["ape", "test", "-s"])
