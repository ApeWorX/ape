import pytest
from ethpm_types import HexBytes


@pytest.fixture
def block(chain):
    return chain.blocks.head


def test_block_dict(block):
    actual = block.dict()
    expected = {
        "baseFeePerGas": 1000000000,
        "difficulty": 0,
        "gasLimit": 30029122,
        "gasUsed": 0,
        "hash": HexBytes("0x7aab51a0a9198dd6d365b7bbbd4733966e73f447195dae6d80419dfc7979e9e5"),
        "num_transactions": 0,
        "number": 0,
        "parentHash": HexBytes(
            "0x0000000000000000000000000000000000000000000000000000000000000000"
        ),
        "size": 548,
        "timestamp": 1685991392,
        "totalDifficulty": 0,
    }
    assert actual == expected


def test_block_json(block):
    actual = block.json()
    expected = (
        '{"baseFeePerGas":1000000000,"difficulty":0,"gasLimit":30029122,"gasUsed":0,'
        f'"hash":"{block.hash.hex()}",'
        '"num_transactions":0,"number":0,'
        f'"parentHash":"{block.parent_hash.hex()}",'
        f'"size":548,"timestamp":{block.timestamp},"totalDifficulty":0}}'
    )
    assert actual == expected
