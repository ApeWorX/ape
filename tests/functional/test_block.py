import pytest


@pytest.fixture
def block(chain):
    return chain.blocks.head


def test_block_dict(block):
    actual = block.model_dump()
    expected = {
        "baseFeePerGas": 1000000000,
        "difficulty": 0,
        "gasLimit": 30029122,
        "gasUsed": 0,
        "hash": block.hash.hex(),
        "num_transactions": 0,
        "number": 0,
        "parentHash": block.parent_hash.hex(),
        "size": block.size,
        "timestamp": block.timestamp,
        "totalDifficulty": 0,
        "transactions": [],
    }
    assert actual == expected


def test_block_json(block):
    actual = block.model_dump_json()
    expected = (
        '{"baseFeePerGas":1000000000,"difficulty":0,"gasLimit":30029122,"gasUsed":0,'
        f'"hash":"{block.hash.hex()}",'
        '"num_transactions":0,"number":0,'
        f'"parentHash":"{block.parent_hash.hex()}",'
        f'"size":{block.size},"timestamp":{block.timestamp},'
        f'"totalDifficulty":0,"transactions":[]}}'
    )
    assert actual == expected
