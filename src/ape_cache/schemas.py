import datetime

from pydantic import BaseModel

# TODO: set these schemas up properly, add in orm mode


class BlocksBase(BaseModel):
    gas_data: bytes
    consensus_data: bytes
    hash: bytes
    number: int
    parent_hash: bytes
    size: int
    timestamp: datetime.datetime


class TransactionsBase(BaseModel):
    hash: bytes
    sender: bytes
    chain_id: int
    block_hash: str
    nonce: int


class ContractEventBase(BaseModel):
    id: int
    contract: bytes
    event_data: bytes
    transaction_hash: bytes
    event_id: bytes
