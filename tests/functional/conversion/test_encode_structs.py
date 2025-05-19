from typing import cast

import pytest
from eth_pydantic_types import HexBytes
from ethpm_types import BaseModel
from ethpm_types.abi import MethodABI

from ape.types.address import AddressType

ABI = MethodABI.model_validate(
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
                    {"name": "d", "type": "address"},
                ],
            }
        ],
    }
)


class Struct(BaseModel):
    a: int
    b: bytes
    c: bool
    d: AddressType


class SimilarStruct(Struct):
    a: int
    b: bytes
    c: bool
    d: AddressType
    e: str  # Gets ignored because not in ABI.


EXPECTED = HexBytes(
    "0000000000000000000000000000000000000000000000000000000000000001"
    "0200000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000001"
    "000000000000000000000000d9b7fdb3fc0a0aa3a507dcf0976bc23d49a9c7a3"
)
ADDRESS = cast(AddressType, "0xD9b7fdb3FC0A0Aa3A507dCf0976bc23D49a9C7A3")
DATA_BY_TYPE_KEY = {
    "tuple": (1, HexBytes("0x02"), True, ADDRESS),
    "dict": {"a": 1, "b": HexBytes("0x02"), "c": True, "d": ADDRESS},
    "object": Struct(a=1, b=HexBytes("0x02"), c=True, d=ADDRESS),
}


@pytest.mark.parametrize("data_type", list(DATA_BY_TYPE_KEY.keys()))
def test_encode_structs(data_type, ethereum):
    data = DATA_BY_TYPE_KEY[data_type]
    encode_calldata = ethereum.encode_calldata
    assert encode_calldata(ABI, data) == EXPECTED


def test_encode_structs_as_tuple_with_unconverted(sender, ethereum):
    normal_data: tuple = DATA_BY_TYPE_KEY["tuple"]  # type: ignore[assignment]
    data = list(normal_data)
    data[-1] = sender
    actual = ethereum.encode_calldata(ABI, normal_data)
    assert actual == EXPECTED


def test_encode_structs_as_dict_with_unconverted(sender, ethereum):
    normal_data: dict = DATA_BY_TYPE_KEY["dict"]  # type: ignore[assignment]
    data = dict(normal_data)
    data["d"] = sender
    actual = ethereum.encode_calldata(ABI, normal_data)
    assert actual == EXPECTED


def test_encode_structs_as_object_with_unconverted(sender, ethereum):
    normal_data: Struct = DATA_BY_TYPE_KEY["object"]  # type: ignore[assignment]
    data = normal_data.model_copy()
    data.d = sender
    actual = ethereum.encode_calldata(ABI, normal_data)
    assert actual == EXPECTED


def test_encode_struct_using_dict_with_more_fields(sender, ethereum):
    normal_data: dict = DATA_BY_TYPE_KEY["dict"]  # type: ignore[assignment]
    data = dict(normal_data)
    data["extra"] = "foobar"  # Should be ignored since not in ABI.
    actual = ethereum.encode_calldata(ABI, normal_data)
    assert actual == EXPECTED


def test_encode_struct_using_object_with_more_fields(sender, ethereum):
    obj = SimilarStruct(a=1, b=HexBytes("0x02"), c=True, d=ADDRESS, e="foobar")
    actual = ethereum.encode_calldata(ABI, obj)
    assert actual == EXPECTED
