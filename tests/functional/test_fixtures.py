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
