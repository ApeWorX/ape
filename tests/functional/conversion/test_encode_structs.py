from ethpm_types.abi import MethodABI
from hexbytes import HexBytes
from pydantic import BaseModel

from ape import networks

ABI = MethodABI.parse_obj(
    {
        "type": "function",
        "name": "test",
        "inputs": [
            {
                "name": "s",
                "type": "tuple",
                "components": [
                    {"name": "a", "type": "uint256"},
                    {"name": "b", "type": "bytes32"},
                    {"name": "c", "type": "bool"},
                ],
            }
        ],
    }
)


class Struct(BaseModel):
    a: int
    b: bytes
    c: bool


EXPECTED = HexBytes(
    "0000000000000000000000000000000000000000000000000000000000000001"
    "3200000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000001"
)


def test_encode_structs():
    encode_calldata = networks.ethereum.encode_calldata

    assert encode_calldata(ABI, (1, b"2", True)) == EXPECTED
    assert encode_calldata(ABI, {"a": 1, "b": b"2", "c": True}) == EXPECTED
    assert encode_calldata(ABI, Struct(a=1, b=b"2", c=True)) == EXPECTED
