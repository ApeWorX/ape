import pytest

from ape.exceptions import BlockNotFoundError
from ape.pytest.fixtures import PytestApeFixtures


@pytest.fixture
def receipt_capture(mocker):
    return mocker.MagicMock()


@pytest.fixture
def fixtures(mocker, receipt_capture):
    return PytestApeFixtures(mocker.MagicMock(), receipt_capture)


@pytest.fixture
def isolation(fixtures):
    return fixtures._isolation()


def test_isolation(isolation, receipt_capture):
    # Set up receipt capture to fail on __exit__
    # AFTER the yield statement. There was a bug
    # where we got a double-yield in this situation.

    receipt_capture.__exit__.side_effect = BlockNotFoundError(0)

    assert next(isolation) is None
    with pytest.raises(StopIteration):
        next(isolation)


def test_isolation_restore_not_implemented(mocker, networks, fixtures):
    isolation = fixtures._isolation()
    mock_provider = mocker.MagicMock()
    mock_provider.restore.side_effect = NotImplementedError
    mock_provider.snapshot.return_value = 123
    orig_provider = networks.active_provider
    networks.active_provider = mock_provider
    fixtures._supports_snapshot = True

    try:
        _ = next(isolation)
        assert mock_provider.snapshot.call_count == 1
        with pytest.raises(StopIteration):
            _ = next(isolation)

        # Is false because of the not-implemented error side-effect.
        assert fixtures._supports_snapshot is False

        isolation = fixtures._isolation()
        _ = next(isolation)
        # It does not call snapshot again.
        assert mock_provider.snapshot.call_count == 1
        with pytest.raises(StopIteration):
            _ = next(isolation)

        assert mock_provider.snapshot.call_count == 1

    finally:
        networks.active_provider = orig_provider


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
        orig_backend = mock_provider._evm_backend
        try:
            mock_provider._evm_backend = mock_evm
            yield mock_provider
        finally:
            mock_provider._evm_backend = orig_backend
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
