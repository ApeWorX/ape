import pytest

from ape.types import ContractLog
from ape.utils import ZERO_ADDRESS

TXN_HASH = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa222222222222222222222222"
BLOCK_HASH = "0x999999998d4f99f68db9999999999da27ed049458b139999999999e910155b99"
BLOCK_NUMBER = 323423
EVENT_NAME = "MyEvent"
LOG_INDEX = 7
RAW_LOG = {
    "block_hash": BLOCK_HASH,
    "block_number": BLOCK_NUMBER,
    "contract_address": ZERO_ADDRESS,
    "event_arguments": {"foo": 0, "bar": 1},
    "log_index": LOG_INDEX,
    "name": EVENT_NAME,
    "transaction_hash": TXN_HASH,
}


@pytest.fixture
def log():
    return ContractLog(**RAW_LOG)


def test_contract_log_serialization(log):
    log = ContractLog.parse_obj(log.dict())
    assert log.contract_address == ZERO_ADDRESS
    assert log.block_hash == BLOCK_HASH
    assert log.block_number == BLOCK_NUMBER
    assert log.name == EVENT_NAME
    assert log.log_index == 7
    assert log.transaction_hash == TXN_HASH


def test_contract_log_access(log):
    assert "foo" in log
    assert "bar" in log
    assert log.foo == log["foo"] == log.get("foo") == 0
    assert log.bar == log["bar"] == log.get("bar") == 1
