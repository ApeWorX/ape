from sqlalchemy import JSON, BigInteger, Column, ForeignKey, Integer, LargeBinary, Numeric
from sqlalchemy.types import String, TypeDecorator

from .base import Base


class HexByteString(TypeDecorator):
    """Convert Python bytestring to string with hexadecimal digits and back for storage."""

    impl = String

    def process_bind_param(self, value, dialect):
        if not isinstance(value, bytes):
            raise TypeError("HexByteString columns support only bytes values.")
        return value.hex()

    def process_result_value(self, value, dialect):
        return bytes.fromhex(value) if value else None


class Blocks(Base):
    __tablename__ = "blocks"  # type: ignore

    hash = Column(HexByteString, primary_key=True, nullable=False)
    num_transactions = Column(Integer, nullable=False)
    number = Column(Integer, nullable=False, index=True)
    parent_hash = Column(HexByteString, nullable=False)
    size = Column(Integer, nullable=False)
    timestamp = Column(BigInteger, index=True)
    gas_limit = Column(Integer, nullable=False)
    gas_used = Column(Integer, nullable=False)
    base_fee = Column(Integer)
    difficulty = Column(Numeric(scale=0), nullable=False)
    total_difficulty = Column(Numeric(scale=0), nullable=False)


class Transactions(Base):
    __tablename__ = "transactions"  # type: ignore

    hash = Column(HexByteString, primary_key=True, index=True)
    sender = Column(HexByteString, nullable=True)
    receiver = Column(HexByteString, nullable=True)
    gas_limit = Column(Integer, nullable=False)
    block_hash = Column(HexByteString, ForeignKey("blocks.hash", ondelete="CASCADE"))
    nonce = Column(Integer, nullable=False)
    value = Column(Integer)
    data = Column(LargeBinary, nullable=True)
    type = Column(Integer)
    signature = Column(HexByteString)


class ContractEvents(Base):
    __tablename__ = "contract_events"  # type: ignore

    id = Column(Integer, primary_key=True, index=True)
    event_name = Column(HexByteString, nullable=False, index=True)
    contract_address = Column(HexByteString, nullable=False, index=True)
    event_arguments = Column(JSON, index=True)
    transaction_hash = Column(HexByteString, nullable=False, index=True)
    block_number = Column(Integer, nullable=False, index=True)
    block_hash = Column(HexByteString, nullable=False, index=True)
    log_index = Column(Integer, nullable=False, index=True)
    transaction_index = Column(Integer, nullable=False, index=True)
