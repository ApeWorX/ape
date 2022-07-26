import pytest
from ethpm_types.abi import EventABI

from ape.types import ContractLog, LogFilter
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
    "event_name": EVENT_NAME,
    "transaction_hash": TXN_HASH,
}
RAW_EVENT_ABI = """
{
  "anonymous": false,
  "inputs": [
    {
      "indexed": true,
      "name": "oldVersion",
      "type": "address"
    },
    {
      "indexed": true,
      "name": "newVersion",
      "type": "address"
    }
  ],
  "name": "StrategyMigrated",
  "type": "event"
}
"""


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


def test_topic_filter_encoding():
    event_abi = EventABI.parse_raw(RAW_EVENT_ABI)
    log_filter = LogFilter.from_event(
        event=event_abi, search_topics={"newVersion": "0x8c44Cc5c0f5CD2f7f17B9Aca85d456df25a61Ae8"}
    )
    assert log_filter.topic_filter == [
        "0x100b69bb6b504e1252e36b375233158edee64d071b399e2f81473a695fd1b021",
        None,
        "0x0000000000000000000000008c44cc5c0f5cd2f7f17b9aca85d456df25a61ae8",
    ]
