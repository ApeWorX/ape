from ethpm_types import HexBytes

from ape.contracts.base import ContractMethodHandler


def test_encode_input_list_for_struct(chain, mocker, owner, method_abi_with_struct_input):
    method = method_abi_with_struct_input
    handler = ContractMethodHandler(contract=mocker.MagicMock(), abis=[method])

    # NOTE: Purposely passing a list for the struct type here!
    #   this is to ensure we can use lists (instead of objects or dictionaries).
    params = [owner.address, b"foo", b"bar"]

    actual = handler.encode_input(owner.address, params, b"", [])
    expected = HexBytes(
        "0x26e0a1960000000000000000000000001e59ce931b4cfea3fe4b875411e280e173cb7a9c"
        "00000000000000000000000000000000000000000000000000000000000000800000000000"
        "00000000000000000000000000000000000000000000000000012000000000000000000000"
        "000000000000000000000000000000000000000001400000000000000000000000001e59ce"
        "931b4cfea3fe4b875411e280e173cb7a9c666f6f0000000000000000000000000000000000"
        "00000000000000000000000000000000000000000000000000000000000000000000000000"
        "00000000000060000000000000000000000000000000000000000000000000000000000000"
        "00036261720000000000000000000000000000000000000000000000000000000000000000"
        "00000000000000000000000000000000000000000000000000000000000000000000000000"
        "000000000000000000000000000000000000000000000000"
    )
    assert actual == expected
