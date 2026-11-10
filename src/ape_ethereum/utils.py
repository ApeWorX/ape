from typing import TYPE_CHECKING

from eth_utils import is_0x_prefixed, is_hex
from web3.exceptions import ContractCustomError, ContractLogicError

if TYPE_CHECKING:
    from web3.types import RPCError

COMPILER_METADATA_KEY_PREFIXES = (
    b"\x64ipfs",
    b"\x65bzzr0",
    b"\x65bzzr1",
    b"\x64solc",
    b"\x65vyper",
)
# Selectors of Solidity's built-in `Error(string)` and `Panic(uint256)` reverts.
REVERT_STRING_SELECTOR = "0x08c379a0"
PANIC_SELECTOR = "0x4e487b71"


def strip_compiler_metadata(bytecode: bytes) -> bytes:
    """
    Strip trailing Solidity or Vyper compiler metadata from bytecode.
    """
    if len(bytecode) < 3:
        return bytecode

    metadata_length = int.from_bytes(bytecode[-2:], "big")
    metadata_start = len(bytecode) - metadata_length - 2
    if metadata_start < 0:
        return bytecode

    metadata = bytecode[metadata_start:-2]
    if not metadata:
        return bytecode

    # Solidity and Vyper metadata are trailing CBOR maps followed by a two-byte
    # big-endian length. Avoid full CBOR parsing here; this is only a fast
    # sanity check that the computed offset starts with a short map containing
    # one of the known compiler metadata keys.
    is_short_cbor_map = 0xA0 < metadata[0] < 0xB8
    if is_short_cbor_map and metadata[1:].startswith(COMPILER_METADATA_KEY_PREFIXES):
        return bytecode[:metadata_start]

    return bytecode


def strip_push_data(bytecode: bytes) -> bytes:
    """
    Strip PUSH1 through PUSH32 arguments from bytecode, leaving opcodes only.
    """
    result = bytearray()
    index = 0
    while index < len(bytecode):
        opcode = bytecode[index]
        result.append(opcode)
        index += 1
        if 0x60 <= opcode <= 0x7F:
            index += opcode - 0x5F

    return bytes(result)


def get_contract_logic_error(rpc_error: "RPCError | str") -> ContractLogicError | None:
    """
    The web3 revert error a JSON-RPC error from ``eth_call`` or ``eth_estimateGas``
    describes, or ``None`` when it is not a revert.
    """
    if isinstance(rpc_error, str):
        return None

    message = rpc_error.get("message") or "execution reverted"
    data = rpc_error.get("data")
    if is_custom_error_data(data):
        return ContractCustomError(data, data=data)

    is_revert = isinstance(data, str) or rpc_error.get("code") == 3
    if is_revert or "execution reverted" in message:
        return ContractLogicError(message, data=data)

    return None


def is_custom_error_data(data) -> bool:
    """
    Whether ``data`` is revert data from a custom error rather than a built-in revert.
    """
    if not isinstance(data, str) or len(data) < 10 or not (is_0x_prefixed(data) and is_hex(data)):
        return False

    return data[:10] not in (REVERT_STRING_SELECTOR, PANIC_SELECTOR)
