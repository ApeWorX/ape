from eth_pydantic_types import HexBytes

from ape.contracts.base import ContractMethodHandler


def test_encode_input_list_for_struct(chain, mocker, owner, method_abi_with_struct_input):
    method = method_abi_with_struct_input
    handler = ContractMethodHandler(contract=mocker.MagicMock(), abis=[method])

    # NOTE: Purposely passing a list for the struct type here!
    #   this is to ensure we can use lists (instead of objects or dictionaries).
    params = [owner.address, b"foo", b"bar"]

    actual = handler.encode_input(owner.address, params, b"", [])
    acct = owner.address.replace("0x", "")
    expected = HexBytes(
        f"0x26e0a196000000000000000000000000{acct}000000000000000"
        f"0000000000000000000000000000000000000000000000080000000"
        f"0000000000000000000000000000000000000000000000000000000"
        f"1200000000000000000000000000000000000000000000000000000"
        f"000000000140000000000000000000000000{acct}666f6f0000000"
        f"0000000000000000000000000000000000000000000000000000000"
        f"0000000000000000000000000000000000000000000000000000000"
        f"0006000000000000000000000000000000000000000000000000000"
        f"0000000000000362617200000000000000000000000000000000000"
        f"0000000000000000000000000000000000000000000000000000000"
        f"0000000000000000000000000000000000000000000000000000000"
        f"00000000000000000000000000000000000000000"
    )
    assert actual == expected
