from typing import Iterator, Union

from eth_account import Account
from eth_account.messages import SignableMessage
from eth_utils import to_bytes, to_hex
from pydantic.dataclasses import dataclass

from ape.types import AddressType


@dataclass(frozen=True)
class _Signature:
    v: int
    r: bytes
    s: bytes

    def __iter__(self) -> Iterator[Union[int, bytes]]:
        # NOTE: Allows tuple destructuring
        yield self.v
        yield self.r
        yield self.s

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} v={self.v} r={to_hex(self.r)} s={to_hex(self.s)}>"

    def encode_vrs(self) -> bytes:
        return to_bytes(self.v) + self.r + self.s

    def encode_rsv(self) -> bytes:
        return self.r + self.s + to_bytes(self.v)


class MessageSignature(_Signature):
    """
    A ECDSA signature (vrs) of a message.
    """


def recover_signer(msg: SignableMessage, sig: MessageSignature) -> AddressType:
    """
    Get the address of the signer.

    Args:
        :class:``SignableMessage``: A formatted and signable message.
        :class:`~ape.types.MessageSignature`MessageSignature: Signature of the message.

    Returns:
        ``AddressType``: address of message signer.
    """
    return Account.recover_message(msg, sig)


class TransactionSignature(_Signature):
    """
    A ECDSA signature (vrs) of a transaction.
    """


__all__ = ["MessageSignature", "TransactionSignature", "SignableMessage"]
