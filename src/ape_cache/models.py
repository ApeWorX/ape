from sqlalchemy import Column, String, Integer, DateTime
from sqlalchemy.sql import func

from base import Base


"""
This is preliminary. To be ironed out
"""


class Blocks(Base):
    __tablename__ = "blocks"

    hash = Column(String, primary_key=True, index=True)
    number = Column(Integer, nullable=False)
    timestamp = Column(DateTime, DateTime(timezone=True), server_default=func.now())


class Transactions(Base):
    __tablename__ = "transactions"

    hash = Column(String, primary_key=True, index=True)
    sender = Column(String, nullable=False)
    chain_id = Column(Integer, nullable=False)
    block_hash = Column(String, nullable=False)
    nonce = Column(Integer, nullable=False)


class ContractEvents(Base):
    __tablename__ = "contract_events"

    id = Column(Integer, primary_key=True, index=True)
    contract = Column(String, nullable=False)
    event_data = Column(String, nullable=False)
    transaction_hash = Column(String, nullable=False)
    event_id = Column(String, nullable=False)
