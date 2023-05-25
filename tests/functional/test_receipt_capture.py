import pytest

from ape.pytest.config import ConfigWrapper
from ape.pytest.fixtures import ReceiptCapture


@pytest.fixture
def pytest_config(mocker):
    return mocker.MagicMock()


@pytest.fixture
def config_wrapper(pytest_config):
    return ConfigWrapper(pytest_config)


@pytest.fixture
def receipt_capture(config_wrapper):
    return ReceiptCapture(config_wrapper)


def test_when_txn_hash_not_exists_does_not_error(receipt_capture):
    actual = receipt_capture.capture("123")
    assert actual is None
