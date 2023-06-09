import pytest


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
        "hash": block.hash.hex(),
        "num_transactions": 0,
        "number": 0,
        "parentHash": block.parent_hash.hex(),
        "size": 548,
        "timestamp": block.timestamp,
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
