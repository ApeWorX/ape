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
