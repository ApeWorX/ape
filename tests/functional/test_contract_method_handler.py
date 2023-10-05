from ethpm_types import HexBytes
from ethpm_types.abi import MethodABI

from ape.contracts.base import ContractMethodHandler


def test_encode_input_list_for_struct(chain, mocker, owner):
    method = MethodABI.parse_obj(
        {
            "type": "function",
            "name": "getTradeableOrderWithSignature",
            "stateMutability": "view",
            "inputs": [
                {"name": "owner", "type": "address", "internalType": "address"},
                {
                    "name": "params",
                    "type": "tuple",
                    "components": [
                        {
                            "name": "handler",
                            "type": "address",
                            "internalType": "contract IConditionalOrder",
                        },
                        {"name": "salt", "type": "bytes32", "internalType": "bytes32"},
                        {"name": "staticInput", "type": "bytes", "internalType": "bytes"},
                    ],
                    "internalType": "struct IConditionalOrder.ConditionalOrderParams",
                },
                {"name": "offchainInput", "type": "bytes", "internalType": "bytes"},
                {"name": "proof", "type": "bytes32[]", "internalType": "bytes32[]"},
            ],
            "outputs": [
                {
                    "name": "order",
                    "type": "tuple",
                    "components": [
                        {"name": "sellToken", "type": "address", "internalType": "contract IERC20"},
                        {"name": "buyToken", "type": "address", "internalType": "contract IERC20"},
                        {"name": "receiver", "type": "address", "internalType": "address"},
                        {"name": "sellAmount", "type": "uint256", "internalType": "uint256"},
                        {"name": "buyAmount", "type": "uint256", "internalType": "uint256"},
                        {"name": "validTo", "type": "uint32", "internalType": "uint32"},
                        {"name": "appData", "type": "bytes32", "internalType": "bytes32"},
                        {"name": "feeAmount", "type": "uint256", "internalType": "uint256"},
                        {"name": "kind", "type": "bytes32", "internalType": "bytes32"},
                        {"name": "partiallyFillable", "type": "bool", "internalType": "bool"},
                        {"name": "sellTokenBalance", "type": "bytes32", "internalType": "bytes32"},
                        {"name": "buyTokenBalance", "type": "bytes32", "internalType": "bytes32"},
                    ],
                    "internalType": "struct GPv2Order.Data",
                },
                {"name": "signature", "type": "bytes", "internalType": "bytes"},
            ],
        }
    )
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
