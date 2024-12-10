from typing import TYPE_CHECKING, Optional

import pytest

from ape.exceptions import BlockNotFoundError
from ape.pytest.fixtures import IsolationManager, PytestApeFixtures
from ape.pytest.utils import Scope

if TYPE_CHECKING:
    from ape.types.vm import SnapshotID


@pytest.fixture
def config_wrapper(mocker):
    return mocker.MagicMock()


@pytest.fixture
def receipt_capture(mocker):
    return mocker.MagicMock()


@pytest.fixture
def isolation_manager(config_wrapper, receipt_capture):
    return IsolationManager(config_wrapper, receipt_capture)


@pytest.fixture
def fixtures(mocker, isolation_manager):
    return PytestApeFixtures(mocker.MagicMock(), isolation_manager)


@pytest.fixture
def isolation(fixtures):
    return fixtures.isolation_manager.isolation(Scope.FUNCTION)


@pytest.fixture
def mock_evm(mocker):
    return mocker.MagicMock()


def test_isolation(isolation, receipt_capture):
    # Set up receipt capture to fail on __exit__
    # AFTER the yield statement. There was a bug
    # where we got a double-yield in this situation.

    receipt_capture.__exit__.side_effect = BlockNotFoundError(0)

    assert next(isolation) is None
    with pytest.raises(StopIteration):
        next(isolation)


def test_isolation_restore_not_implemented(mocker, networks, fixtures):
    isolation = fixtures.isolation_manager.isolation(Scope.FUNCTION)
    mock_provider = mocker.MagicMock()
    mock_provider.restore.side_effect = NotImplementedError
    mock_provider.snapshot.return_value = 123
    orig_provider = networks.active_provider
    networks.active_provider = mock_provider
    fixtures.isolation_manager.supported = True

    try:
        _ = next(isolation)
        assert mock_provider.snapshot.call_count == 1
        with pytest.raises(StopIteration):
            _ = next(isolation)

        # Is false because of the not-implemented error side-effect.
        assert fixtures.isolation_manager.supported is False

        isolation = fixtures.isolation_manager.isolation(Scope.FUNCTION)
        _ = next(isolation)
        # It does not call snapshot again.
        assert mock_provider.snapshot.call_count == 1
        with pytest.raises(StopIteration):
            _ = next(isolation)

        assert mock_provider.snapshot.call_count == 1

    finally:
        networks.active_provider = orig_provider


@pytest.mark.parametrize("snapshot_id", (0, 1, "123"))
def test_isolation_snapshot_id_types(snapshot_id, fixtures):
    class IsolationManagerWithCustomSnapshot(IsolationManager):
        take_call_count = 0
        restore_call_count = 0
        restore_called_with = []

        def take_snapshot(self) -> Optional["SnapshotID"]:
            self.take_call_count += 1
            return snapshot_id

        def restore(self, scope: Scope):
            self.restore_call_count += 1
            self.restore_called_with.append(scope)

    isolation_manager = IsolationManagerWithCustomSnapshot(
        fixtures.isolation_manager.config_wrapper,
        fixtures.isolation_manager.receipt_capture,
    )
    isolation_context = isolation_manager.isolation(Scope.FUNCTION)
    next(isolation_context)  # Enter.
    assert isolation_manager.take_call_count == 1
    assert isolation_manager.restore_call_count == 0
    next(isolation_context, None)  # Exit.
    assert isolation_manager.restore_called_with == [Scope.FUNCTION]


def test_isolation_when_snapshot_fails_avoids_restore(fixtures):
    class IsolationManagerFailingAtSnapshotting(IsolationManager):
        take_called = False
        restore_called = False

        def take_snapshot(self) -> Optional["SnapshotID"]:
            self.take_called = True
            raise NotImplementedError()

        def restore(self, scope: Scope):
            self.restore_called = True

    isolation_manager = IsolationManagerFailingAtSnapshotting(
        fixtures.isolation_manager.config_wrapper,
        fixtures.isolation_manager.receipt_capture,
    )
    isolation_context = isolation_manager.isolation(Scope.FUNCTION)
    next(isolation_context)  # Enter.
    assert isolation_manager.take_called
    assert not isolation_manager.restore_called
    next(isolation_context, None)  # Exit.
    # It doesn't even try!
    assert not isolation_manager.restore_called


def test_isolation_restore_fails_avoids_snapshot_next_time(fixtures):
    chain_snapshots = {}

    class IsolationManagerFailingAtRestoring(IsolationManager):
        take_called = False
        restore_called = False

        def take_snapshot(self) -> Optional["SnapshotID"]:
            self.take_called = True
            chain_snapshots[self.provider.chain_id] = ["123"]
            return "123"

        def _restore(self, snapshot_id: "SnapshotID"):
            self.restore_called = True
            raise NotImplementedError()

        def reset_mock(self):
            self.take_called = False
            self.restore_called = False

    isolation_manager = IsolationManagerFailingAtRestoring(
        fixtures.isolation_manager.config_wrapper,
        fixtures.isolation_manager.receipt_capture,
        chain_snapshots=chain_snapshots,
    )
    isolation_context = isolation_manager.isolation(Scope.FUNCTION)
    next(isolation_context)  # Enter.
    # Snapshot works, we get this far.
    assert isolation_manager.take_called
    assert not isolation_manager.restore_called

    # At this point, it realized snapshotting is no-go.
    next(isolation_context, None)  # Exit.
    assert isolation_manager.restore_called

    isolation_manager.reset_mock()
    isolation_context = isolation_manager.isolation(Scope.FUNCTION)
    next(isolation_context)  # Enter again.

    # This time, snapshotting is NOT attempted.
    assert not isolation_manager.take_called
    assert not isolation_manager.restore_called


def test_isolation_supported_flag_set_after_successful_snapshot(fixtures):
    """
    Testing the unusual case where `.supported` was changed manually after
    a successful snapshot and before the restore attempt.
    """

    class CustomIsolationManager(IsolationManager):
        take_called = False
        restore_called = False

        def take_snapshot(self) -> Optional["SnapshotID"]:
            self.take_called = True
            return 123

        def restore(self, scope: Scope):
            self.restore_called = True

    isolation_manager = CustomIsolationManager(
        fixtures.isolation_manager.config_wrapper,
        fixtures.isolation_manager.receipt_capture,
    )
    isolation_context = isolation_manager.isolation(Scope.FUNCTION)
    next(isolation_context)  # Enter.
    assert isolation_manager.take_called
    assert not isolation_manager.restore_called

    # HACK: Change the flag manually to show it will avoid
    #   the restore.
    isolation_manager.supported = False
    isolation_manager.take_called = False  # Reset
    next(isolation_context, None)  # Exit.
    # Even though snapshotting worked, the flag was changed,
    # and so the restore never gets attempted.
    assert not isolation_manager.take_called
