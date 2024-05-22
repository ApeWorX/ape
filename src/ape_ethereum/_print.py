"""Utilities to extract debug log data from Vyper's print() and the Hardhat Solidity console.log
calls.

There are two different implementations of the console.log functionality. Vyper's print() and
Hardhat's console.sol contract. Both send staticcalls to a specific non-existent contract that we
can read from the call tree.

Vyper encodes these calls as `log(string,bytes)`. Where the first argument is an ABI signature
(e.g. "(uint256,uint8,string)") and the second arg is the printed data. This allows for a simple ABI
and very dynamic output.

Hardhat's console.sol has a strict ABI (unless patched :-/) that mixes and matches all the basic
datatypes to overload all calls to `log()`.

References
----------
- Vyper `print()`: https://docs.vyperlang.org/en/latest/built-in-functions.html#print
- Hardhat's `console.sol`: https://github.com/NomicFoundation/hardhat/blob/e6a42cf330863a6c64624baedd82fc6c5218a20a/packages/hardhat-core/console.sol#L4  # noqa: E501
- Discussion on dynamic ABI encoding (Vyper-style) for log calls: https://github.com/NomicFoundation/hardhat/issues/2666  # noqa: E501
"""

from typing import Any, Iterable, Tuple, cast

from eth_abi import decode
from eth_typing import ChecksumAddress
from eth_utils import decode_hex
from ethpm_types import ContractType, MethodABI
from typing_extensions import TypeGuard

import ape
from ape.types import CallTreeNode

from ._console_log_abi import CONSOLE_LOG_ABI

CONSOLE_CONTRACT_ID = cast(ChecksumAddress, "0x000000000000000000636F6e736F6c652e6c6f67")
VYPER_PRINT_METHOD_ID = "0x23cdd8e8"  # log(string,bytes)

console_contract = ContractType(abi=CONSOLE_LOG_ABI, contractName="console")


def is_console_log(call: Any) -> TypeGuard[CallTreeNode]:
    """Determine if a call is a starndard console.log() call"""
    return (
        isinstance(call, CallTreeNode)
        and call.contract_id == CONSOLE_CONTRACT_ID
        and call.method_id in console_contract.identifier_lookup
    )


def is_vyper_print(call: Any) -> TypeGuard[CallTreeNode]:
    """Determine if a call is a starndard Vyper print() call"""
    if (
        isinstance(call, CallTreeNode)
        and call.contract_id == CONSOLE_CONTRACT_ID
        and call.method_id == VYPER_PRINT_METHOD_ID
        and isinstance(call.inputs, str)
    ):
        bcalldata = decode_hex(call.inputs)
        schema, _ = decode(["string", "bytes"], bcalldata)
        try:
            # Now we look at the first arg to try and determine if it's an ABI signature
            first_type = schema.strip("()").split(",")[0]
            # TODO: Tighten this up.  This is not entirely accurate, but should mostly get us there.
            if (
                first_type.startswith("uint")
                or first_type.startswith("int")
                or first_type.startswith("bytes")
                or first_type == "string"
            ):
                return True
        except IndexError:
            # Empty string as first arg?
            pass
    return False


def console_log(method_abi: MethodABI, calldata: str) -> Tuple[Any]:
    """Return logged data for console.log() calls"""
    bcalldata = decode_hex(calldata)
    data = ape.networks.ethereum.decode_calldata(method_abi, bcalldata)
    return tuple(data.values())


def vyper_print(calldata: str) -> Tuple[Any]:
    """Return logged data for print() calls"""
    bcalldata = decode_hex(calldata)
    schema, payload = decode(["string", "bytes"], bcalldata)
    data = decode(schema.strip("()").split(","), payload)
    return tuple(data)


def extract_debug_logs(call_tree: CallTreeNode) -> Iterable[Tuple[Any]]:
    """Filter calls to console.log() and print() from a transactions call tree"""
    for call in call_tree.calls:
        if is_vyper_print(call) and call.inputs is not None:
            yield vyper_print(call.inputs)
        elif is_console_log(call) and call.inputs is not None:
            assert call.method_id is not None  # is_console_log check already checked
            method_abi = console_contract.identifier_lookup.get(call.method_id)
            if isinstance(method_abi, MethodABI):
                yield console_log(method_abi, call.inputs)
        elif call.calls is not None:
            yield from extract_debug_logs(call)
