from sqlalchemy import Column, String, Integer, DateTime, ForeignKey
from sqlalchemy.sql import func

from .base import Base


class Blocks(Base):
    __tablename__ = "blocks"

    gas_data = Column(String)
    consensus_data: Column(String)
    hash = Column(String, primary_key=True, index=True)
    chain_id = Column(Integer, nullable=False)
    number = Column(Integer, nullable=False)
    parent_hash = Column(String)
    size = Column(Integer)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class Transactions(Base):
    __tablename__ = "transactions"

    hash = Column(String, primary_key=True, index=True)
    sender = Column(String, nullable=False)
    chain_id = Column(Integer, nullable=False)
    block_hash = Column(String, ForeignKey("blocks.hash", ondelete="CASCADE"))
    nonce = Column(Integer, nullable=False)


class ContractEvents(Base):
    __tablename__ = "contract_events"

    id = Column(Integer, primary_key=True, index=True)
    contract = Column(String, nullable=False)
    event_data = Column(String, nullable=False)
    transaction_hash = Column(String, ForeignKey("transactions.hash", ondelete="CASCADE"), nullable=False)
    chain_id = Column(Integer, nullable=False)
    event_id = Column(String, nullable=False)
