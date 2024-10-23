from collections.abc import Iterator
from typing import Optional, Union

from eth_account import Account
from eth_account.messages import SignableMessage
from eth_pydantic_types import HexBytes
from eth_utils import to_bytes, to_hex
from pydantic.dataclasses import dataclass

from ape.utils.misc import as_our_module, log_instead_of_fail

try:
    # Only on Python 3.11
    from typing import Self  # type: ignore
except ImportError:
    from typing_extensions import Self  # type: ignore

from ape.types.address import AddressType

# Fix 404 in doc link.
as_our_module(
    SignableMessage,
    doc_str=(SignableMessage.__doc__ or "").replace(
        "EIP-191_", "`EIP-191 <https://eips.ethereum.org/EIPS/eip-191>`__"
    ),
)


# Improve repr to force hexstr for body instead of raw bytes.
def signable_message_repr(msg) -> str:
    name = getattr(SignableMessage, "__name__", "SignableMessage")
    default_value = "<unknown!>"  # Shouldn't happen
    version_str = _bytes_to_human_str(msg.version) or default_value
    header_str = _bytes_to_human_str(msg.header) or default_value
    body_str = _bytes_to_human_str(msg.body) or default_value
    return f"{name}(" f'version="{version_str}", header="{header_str}", body="{body_str}")'


SignableMessage.__repr__ = signable_message_repr  # type: ignore[method-assign]


def _bytes_to_human_str(bytes_value: bytes) -> Optional[str]:
    try:
        # Try as text
        return bytes_value.decode("utf8")
    except Exception:
        pass

    try:
        # Try as hex
        return to_hex(bytes_value)
    except Exception:
        pass

    try:
        # Try normal str
        return str(bytes_value)
    except Exception:
        pass

    return None


def _left_pad_bytes(val: bytes, num_bytes: int) -> bytes:
    return b"\x00" * (num_bytes - len(val)) + val if len(val) < num_bytes else val


@dataclass(frozen=True)
class _Signature:
    v: int
    """
    The version byte (``v``) in an Ethereum-style ECDSA signature.
    """

    r: bytes
    """
    The random point (``r``) in an ECDSA signature.
    """

    s: bytes
    """
    The signature proof point (``s``) in an ECDSA signature.
    """

    def __iter__(self) -> Iterator[Union[int, bytes]]:
        # NOTE: Allows tuple destructuring
        yield self.v
        yield self.r
        yield self.s

    @classmethod
    def from_rsv(cls, rsv: HexBytes) -> Self:
        # NOTE: Values may be padded.
        if len(rsv) != 65:
            raise ValueError("Length of RSV bytes must be 65.")

        return cls(r=HexBytes(rsv[:32]), s=HexBytes(rsv[32:64]), v=rsv[64])

    @classmethod
    def from_vrs(cls, vrs: HexBytes) -> Self:
        # NOTE: Values may be padded.
        if len(vrs) != 65:
            raise ValueError("Length of VRS bytes must be 65.")

        return cls(v=vrs[0], r=HexBytes(vrs[1:33]), s=HexBytes(vrs[33:]))

    @log_instead_of_fail(default="<_Signature>")
    def __repr__(self) -> str:
        class_name = getattr(type(self), "__name__", "_Signature")
        return f"<{class_name} v={self.v} r={to_hex(self.r)} s={to_hex(self.s)}>"

    def encode_vrs(self) -> bytes:
        return to_bytes(self.v) + _left_pad_bytes(self.r, 32) + _left_pad_bytes(self.s, 32)

    def encode_rsv(self) -> bytes:
        return _left_pad_bytes(self.r, 32) + _left_pad_bytes(self.s, 32) + to_bytes(self.v)


class MessageSignature(_Signature):
    """
    A ECDSA signature (vrs) of a message.
    """


def recover_signer(msg: SignableMessage, sig: MessageSignature) -> AddressType:
    """
    Get the address of the signer.

    Args:
        msg (:class:`~ape.types.signatures.SignableMessage`): A formatted and signable
          message.
        sig (:class:`~ape.types.signatures.MessageSignature`): Signature of the message.

    Returns:
        :class:`~ape.types.address.AddressType`: address of message signer.
    """
    return Account.recover_message(msg, sig)


class TransactionSignature(_Signature):
    """
    A ECDSA signature (vrs) of a transaction.
    """


__all__ = ["MessageSignature", "TransactionSignature", "SignableMessage"]
