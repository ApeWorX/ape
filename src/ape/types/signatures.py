from typing import Iterator, Union

from dataclassy import dataclass
from eth_account.messages import SignableMessage  # type: ignore
from eth_utils import to_bytes


@dataclass(frozen=True, slots=True, kwargs=True)
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
        return f"<{self.__class__.__name__} v={self.v} r={self.r.hex()} s={self.s.hex()}>"

    def encode_vrs(self) -> bytes:
        return to_bytes(self.v) + self.r + self.s

    def encode_rsv(self) -> bytes:
        return self.r + self.s + to_bytes(self.v)


class MessageSignature(_Signature):
    pass


class TransactionSignature(_Signature):
    pass


_ = SignableMessage
