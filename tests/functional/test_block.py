import pytest
from eth_pydantic_types import HexBytes

from ape_ethereum.ecosystem import Block


@pytest.fixture
def block(chain):
    return chain.blocks.head


def test_block(eth_tester_provider, vyper_contract_instance):
    data = eth_tester_provider.web3.eth.get_block("latest")
    actual = Block.model_validate(data)
    assert actual.hash == data["hash"]
    assert actual.number == data["number"]


def test_block_dict(block):
    actual = block.model_dump(mode="json")
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
        "transactions": [],
        "uncles": [],
    }
    assert actual == expected


def test_block_json(block):
    actual = block.model_dump_json()
    expected = (
        '{"baseFeePerGas":1000000000,"difficulty":0,"gasLimit":30029122,"gasUsed":0,'
        f'"hash":"{block.hash.hex()}",'
        '"num_transactions":0,"number":0,'
        f'"parentHash":"{block.parent_hash.hex()}",'
        f'"size":548,"timestamp":{block.timestamp},'
        f'"totalDifficulty":0,"transactions":[],"uncles":[]}}'
    )
    assert actual == expected


def test_block_calculate_size(block):
    original = block.model_dump(by_alias=True)
    size = original.pop("size")

    # Show size works normally (validated when passed in as a field).
    assert size > 0
    assert block.size == size

    # Show we can also calculate size if it is missing.
    actual = block.model_validate(original)  # re-init without size.
    assert actual.size == size

    original["size"] = 123
    new_block = Block.model_validate(original)
    assert new_block.size == 123  # Show no clashing.
    assert actual.size == size  # Show this hasn't changed.


def test_block_uncles(block):
    data = block.model_dump(by_alias=True)
    uncles = [HexBytes("0xb983ecae1ed260dd08d108653912a9138bdce56c78aa7d78ee4fca70c2c8767b")]
    data["uncles"] = uncles
    actual = Block.model_validate(data)
    assert actual.uncles == uncles
