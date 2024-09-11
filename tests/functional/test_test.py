import pytest

from ape.pytest.fixtures import PytestApeFixtures
from ape_test import ApeTestConfig


class TestApeTestConfig:
    def test_balance_set_from_currency_str(self):
        curr_val = "10 Eth"
        data = {"balance": curr_val}
        cfg = ApeTestConfig.model_validate(data)
        actual = cfg.balance
        expected = 10_000_000_000_000_000_000  # 10 ETH in WEI
        assert actual == expected


class TestPytestApeFixtures:
    @pytest.fixture
    def mock_config_wrapper(self, mocker):
        return mocker.MagicMock()

    @pytest.fixture
    def mock_receipt_capture(self, mocker):
        return mocker.MagicMock()

    @pytest.fixture
    def mock_evm(self, mocker):
        return mocker.MagicMock()

    @pytest.fixture
    def fixtures(self, mock_config_wrapper, mock_receipt_capture):
        return PytestApeFixtures(mock_config_wrapper, mock_receipt_capture)

    @pytest.fixture
    def use_mock_provider(self, networks, mock_provider, mock_evm):
        mock_provider._web3.eth.get_block.return_value = {
            "timestamp": 123,
            "gasLimit": 0,
            "gasUsed": 0,
            "number": 0,
        }
        orig_provider = networks.active_provider
        networks.active_provider = mock_provider
        mock_provider._evm_backend = mock_evm
        yield mock_provider
        networks.active_provider = orig_provider

    @pytest.mark.parametrize("snapshot_id", (0, 1, "123"))
    def test_isolation(self, snapshot_id, networks, use_mock_provider, fixtures, mock_evm):
        mock_evm.take_snapshot.return_value = snapshot_id
        isolation_context = fixtures._isolation()
        next(isolation_context)  # Enter.
        assert mock_evm.take_snapshot.call_count == 1
        assert mock_evm.revert_to_snapshot.call_count == 0
        next(isolation_context, None)  # Exit.
        mock_evm.revert_to_snapshot.assert_called_once_with(snapshot_id)

    def test_isolation_when_snapshot_fails_avoids_restore(
        self, networks, use_mock_provider, fixtures, mock_evm
    ):
        mock_evm.take_snapshot.side_effect = NotImplementedError
        isolation_context = fixtures._isolation()
        next(isolation_context)  # Enter.
        assert mock_evm.take_snapshot.call_count == 1
        assert mock_evm.revert_to_snapshot.call_count == 0
        next(isolation_context, None)  # Exit.
        # It doesn't even try!
        assert mock_evm.revert_to_snapshot.call_count == 0

    def test_isolation_restore_fails_avoids_snapshot_next_time(
        self, networks, use_mock_provider, fixtures, mock_evm
    ):
        mock_evm.take_snapshot.return_value = 123
        mock_evm.revert_to_snapshot.side_effect = NotImplementedError
        isolation_context = fixtures._isolation()
        next(isolation_context)  # Enter.
        # Snapshot works, we get this far.
        assert mock_evm.take_snapshot.call_count == 1
        assert mock_evm.revert_to_snapshot.call_count == 0

        # At this point, it is realized snapshotting is no-go.
        mock_evm.take_snapshot.reset_mock()
        next(isolation_context, None)  # Exit.
        isolation_context = fixtures._isolation()
        next(isolation_context)  # Enter again.
        # This time, snapshotting is NOT attempted.
        assert mock_evm.take_snapshot.call_count == 0

    def test_isolation_supports_flag_set_after_successful_snapshot(
        self, networks, use_mock_provider, fixtures, mock_evm
    ):
        """
        Testing the unusual case where `._supports_snapshot` was changed manually after
        a successful snapshot and before the restore attempt.
        """
        mock_evm.take_snapshot.return_value = 123
        isolation_context = fixtures._isolation()
        next(isolation_context)  # Enter.
        assert mock_evm.take_snapshot.call_count == 1
        assert mock_evm.revert_to_snapshot.call_count == 0

        # HACK: Change the flag manually to show it will avoid
        #   the restore.
        fixtures._supports_snapshot = False

        next(isolation_context, None)  # Exit.
        # Even though snapshotting worked, the flag was changed,
        # and so the restore never gets attempted.
        assert mock_evm.revert_to_snapshot.call_count == 0
