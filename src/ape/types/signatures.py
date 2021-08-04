from typing import Iterator

from dataclassy import dataclass
from eth_account.messages import SignableMessage  # type: ignore


@dataclass(frozen=True, slots=True, kwargs=True)
class _Signature:
    v: int
    r: bytes
    s: bytes

    def __iter__(self) -> Iterator[bytes]:
        yield bytes(self.v)
        yield self.r
        yield self.s

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} v={self.v} r={self.r.hex()} s={self.s.hex()}>"

    def encode_vrs(self) -> bytes:
        return bytes(self.v) + self.r + self.s

    def encode_rsv(self) -> bytes:
        return self.r + self.s + bytes(self.v)


class MessageSignature(_Signature):
    pass


class TransactionSignature(_Signature):
    pass


_ = SignableMessage
