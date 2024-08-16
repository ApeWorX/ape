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

from collections.abc import Iterable
from typing import Any, cast

from eth_abi import decode
from eth_typing import ChecksumAddress
from eth_utils import add_0x_prefix, decode_hex, to_hex
from ethpm_types import ContractType, MethodABI
from evm_trace import CallTreeNode
from hexbytes import HexBytes
from typing_extensions import TypeGuard

import ape
from ape_ethereum._console_log_abi import CONSOLE_LOG_ABI

CONSOLE_ADDRESS = cast(ChecksumAddress, "0x000000000000000000636F6e736F6c652e6c6f67")
VYPER_PRINT_METHOD_ID = HexBytes("0x23cdd8e8")  # log(string,bytes)

console_contract = ContractType(abi=CONSOLE_LOG_ABI, contractName="console")


def is_console_log(call: CallTreeNode) -> TypeGuard[CallTreeNode]:
    """Determine if a call is a standard console.log() call"""
    return (
        call.address == HexBytes(CONSOLE_ADDRESS)
        and to_hex(call.calldata[:4]) in console_contract.identifier_lookup
    )


def is_vyper_print(call: CallTreeNode) -> TypeGuard[CallTreeNode]:
    """Determine if a call is a standard Vyper print() call"""
    if call.address != HexBytes(CONSOLE_ADDRESS) or call.calldata[:4] != VYPER_PRINT_METHOD_ID:
        return False

    schema, _ = decode(["string", "bytes"], call.calldata[4:])
    types = schema.strip("()").split(",")

    # Now we look at the first arg to try and determine if it's an ABI signature
    # TODO: Tighten this up. This is not entirely accurate, but should mostly get us there.
    return len(types) > 0 and (
        types[0].startswith("uint")
        or types[0].startswith("int")
        or types[0].startswith("bytes")
        or types[0] == "string"
    )


def console_log(method_abi: MethodABI, calldata: str) -> tuple[Any]:
    """Return logged data for console.log() calls"""
    bcalldata = decode_hex(calldata)
    data = ape.networks.ethereum.decode_calldata(method_abi, bcalldata)
    return tuple(data.values())


def vyper_print(calldata: str) -> tuple[Any]:
    """Return logged data for print() calls"""
    schema, payload = decode(["string", "bytes"], HexBytes(calldata))
    data = decode(schema.strip("()").split(","), payload)
    return tuple(data)


def extract_debug_logs(call: CallTreeNode) -> Iterable[tuple[Any]]:
    """Filter calls to console.log() and print() from a transactions call tree"""
    if is_vyper_print(call) and call.calldata is not None:
        yield vyper_print(add_0x_prefix(to_hex(call.calldata[4:])))

    elif is_console_log(call) and call.calldata is not None:
        method_abi = console_contract.identifier_lookup.get(to_hex(call.calldata[:4]))
        if isinstance(method_abi, MethodABI):
            yield console_log(method_abi, to_hex(call.calldata[4:]))

    elif call.calls is not None:
        for sub_call in call.calls:
            yield from extract_debug_logs(sub_call)
