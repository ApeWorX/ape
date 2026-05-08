COMPILER_METADATA_KEY_PREFIXES = (
    b"\x64ipfs",
    b"\x65bzzr0",
    b"\x65bzzr1",
    b"\x64solc",
    b"\x65vyper",
)


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
