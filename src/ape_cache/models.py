from sqlalchemy.types import Column, DateTime, ForeignKey, Integer, String  # type: ignore

from .base import Base


class Blocks(Base):
    __tablename__ = "blocks"  # type: ignore

    hash = Column(String, primary_key=True, nullable=False)
    gas_data = Column(String, nullable=False)
    consensus_data = Column(String, nullable=False)
    number = Column(Integer, nullable=False, index=True)
    parent_hash = Column(String, nullable=False)
    size = Column(Integer, nullable=False)
    timestamp = Column(DateTime, index=True)


class Transactions(Base):
    __tablename__ = "transactions"  # type: ignore

    hash = Column(String, primary_key=True, index=True)
    sender = Column(String, nullable=False)
    block_hash = Column(String, ForeignKey("blocks.hash", ondelete="CASCADE"))
    nonce = Column(Integer, nullable=False)


class ContractEvents(Base):
    __tablename__ = "contract_events"  # type: ignore

    id = Column(Integer, primary_key=True, index=True)
    contract = Column(String, nullable=False)
    event_data = Column(String, nullable=False)
    transaction_hash = Column(
        String,
        ForeignKey("transactions.hash", ondelete="CASCADE"),
        nullable=False,
    )
    event_id = Column(String, nullable=False)
