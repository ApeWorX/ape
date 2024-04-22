from typing import Dict

import pytest
from eth_utils import to_hex
from ethpm_types.abi import EventABI
from hexbytes import HexBytes
from pydantic import BaseModel

from ape.types import (
    AddressType,
    ContractLog,
    LogFilter,
    MessageSignature,
    SignableMessage,
    TransactionSignature,
)
from ape.utils import ZERO_ADDRESS

TXN_HASH = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa222222222222222222222222"
BLOCK_HASH = "0x999999998d4f99f68db9999999999da27ed049458b139999999999e910155b99"
BLOCK_NUMBER = 323423
EVENT_NAME = "MyEvent"
LOG_INDEX = 7
TXN_INDEX = 2
RAW_LOG: Dict = {
    "block_hash": BLOCK_HASH,
    "block_number": BLOCK_NUMBER,
    "contract_address": ZERO_ADDRESS,
    "event_arguments": {"foo": 0, "bar": 1},
    "log_index": LOG_INDEX,
    "event_name": EVENT_NAME,
    "transaction_hash": TXN_HASH,
    "transaction_index": TXN_INDEX,
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


@pytest.fixture
def signable_message():
    version = b"E"
    header = b"thereum Signed Message:\n32"
    body = (
        b"\x86\x05\x99\xc6\xfa\x0f\x05|po(\x1f\xe3\x84\xc0\x0f"
        b"\x13\xb2\xa6\x91\xa3\xb8\x90\x01\xc0z\xa8\x17\xbe'\xf3\x13"
    )
    return SignableMessage(version=version, header=header, body=body)


@pytest.fixture
def signature(owner, signable_message):
    return owner.sign_message(signable_message)


def test_contract_log_serialization(log, zero_address):
    obj = ContractLog.model_validate(log.model_dump())
    assert obj.contract_address == zero_address
    assert obj.block_hash == BLOCK_HASH
    assert obj.block_number == BLOCK_NUMBER
    assert obj.event_name == EVENT_NAME
    assert obj.log_index == 7
    assert obj.transaction_hash == TXN_HASH
    assert obj.transaction_index == TXN_INDEX


def test_contract_log_serialization_with_hex_strings_and_non_checksum_addresses(log, zero_address):
    data = log.model_dump()
    data["log_index"] = to_hex(log.log_index)
    data["transaction_index"] = to_hex(log.transaction_index)
    data["block_number"] = to_hex(log.block_number)
    data["contract_address"] = log.contract_address.lower()

    obj = ContractLog(**data)

    assert obj.contract_address == zero_address
    assert obj.block_hash == BLOCK_HASH
    assert obj.block_number == BLOCK_NUMBER
    assert obj.event_name == EVENT_NAME
    assert obj.log_index == 7
    assert obj.transaction_hash == TXN_HASH
    assert obj.transaction_index == TXN_INDEX


def test_contract_log_str(log):
    obj = ContractLog.model_validate(log.model_dump())
    assert str(obj) == "MyEvent(foo=0 bar=1)"


def test_contract_log_repr(log):
    obj = ContractLog.model_validate(log.model_dump())
    assert repr(obj) == "<MyEvent foo=0 bar=1>"


def test_contract_log_access(log):
    assert "foo" in log
    assert "bar" in log
    assert log.foo == log["foo"] == log.get("foo") == 0
    assert log.bar == log["bar"] == log.get("bar") == 1


def test_topic_filter_encoding():
    event_abi = EventABI.model_validate_json(RAW_EVENT_ABI)
    log_filter = LogFilter.from_event(
        event=event_abi, search_topics={"newVersion": "0x8c44Cc5c0f5CD2f7f17B9Aca85d456df25a61Ae8"}
    )
    assert log_filter.topic_filter == [
        "0x100b69bb6b504e1252e36b375233158edee64d071b399e2f81473a695fd1b021",
        None,
        "0x0000000000000000000000008c44cc5c0f5cd2f7f17b9aca85d456df25a61ae8",
    ]


def test_signature_repr():
    signature = TransactionSignature(v=0, r=b"123", s=b"456")
    assert repr(signature) == "<TransactionSignature v=0 r=0x313233 s=0x343536>"


def test_signable_message_repr(signable_message):
    actual = repr(signable_message)
    expected_version = "E"
    expected_header = "thereum Signed Message:\n32"
    expected_body = "0x860599c6fa0f057c706f281fe384c00f13b2a691a3b89001c07aa817be27f313"
    expected = (
        f'SignableMessage(version="{expected_version}", header="{expected_header}", '
        f'body="{expected_body}")'
    )

    assert actual == expected


def test_signature_from_rsv_and_vrs(signature):
    rsv = signature.encode_rsv()
    vrs = signature.encode_vrs()

    # NOTE: Type declaring for sake of ensuring
    #   type-checking works since class-method is
    #   defined in base-class.
    from_rsv: MessageSignature = signature.from_rsv(rsv)
    from_vrs: MessageSignature = signature.from_vrs(vrs)
    assert from_rsv == from_vrs == signature


def test_address_type(owner):
    class MyModel(BaseModel):
        addr: AddressType

    # Show str works.
    instance_str = MyModel(addr=owner.address)
    assert instance_str.addr == owner.address

    # Show hex bytes work.
    instance_hex_bytes = MyModel(addr=HexBytes(owner.address))
    assert instance_hex_bytes.addr == owner.address

    # Show raw bytes work.
    instance_bytes = MyModel(addr=bytes.fromhex(owner.address[2:]))
    assert instance_bytes.addr == owner.address

    # Show int works.
    instance_bytes = MyModel(addr=int(owner.address, 16))
    assert instance_bytes.addr == owner.address
