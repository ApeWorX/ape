import pytest
from eth_pydantic_types import HexBytes
from eth_utils import to_hex
from web3.types import BlockData

from ape_ethereum.ecosystem import Block


@pytest.fixture
def block(chain):
    return chain.blocks.head


def test_block(eth_tester_provider, vyper_contract_instance):
    data = eth_tester_provider.web3.eth.get_block("latest")
    actual = Block.model_validate(data)
    assert actual.hash == data["hash"]
    assert actual.number == data["number"]


@pytest.mark.parametrize("mode", ("json", "python"))
def test_model_dump(block, mode):
    actual = block.model_dump(mode=mode)
    expected = {
        "baseFeePerGas": 1000000000,
        "difficulty": 0,
        "gasLimit": 30029122,
        "gasUsed": 0,
        "hash": to_hex(block.hash),
        "num_transactions": 0,
        "number": 0,
        "parentHash": to_hex(block.parent_hash),
        "size": block.size,
        "timestamp": block.timestamp,
        "totalDifficulty": 0,
        "transactions": [],
        "uncles": [],
    }
    assert actual == expected


def test_model_dump_json(block):
    actual = block.model_dump_json()
    expected = (
        '{"baseFeePerGas":1000000000,"difficulty":0,"gasLimit":30029122,"gasUsed":0,'
        f'"hash":"{to_hex(block.hash)}",'
        '"num_transactions":0,"number":0,'
        f'"parentHash":"{to_hex(block.parent_hash)}",'
        f'"size":{block.size},"timestamp":{block.timestamp},'
        '"totalDifficulty":0,"transactions":[],"uncles":[]}'
    )
    assert actual == expected


@pytest.mark.parametrize("size", (123, HexBytes(123), to_hex(123)))
def test_size(block, size):
    block._size = size
    dictionary_python = block.model_dump(mode="python")
    dictionary_json = block.model_dump(mode="json")
    jons_str = block.model_dump_json()
    assert dictionary_python["size"] == 123
    assert dictionary_json["size"] == 123
    assert '"size":123' in jons_str

    # Show the same when validated with size in the model.
    data = block.model_dump()
    data["size"] = size
    new_block = Block.model_validate(data)
    dictionary_python = new_block.model_dump(mode="python")
    dictionary_json = new_block.model_dump(mode="json")
    jons_str = new_block.model_dump_json()
    assert dictionary_python["size"] == 123
    assert dictionary_json["size"] == 123
    assert '"size":123' in jons_str


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


def test_model_dump_and_validate(block):
    model_dump = block.model_dump(by_alias=True)
    model_validate = Block.model_validate(model_dump)
    assert model_validate == block
    # Validate existing model.
    model_validate_from_model = Block.model_validate(block)
    assert model_validate_from_model == block


def test_model_validate_web3_block():
    """
    Show we have good compatibility with web3.py native types.
    """
    data = BlockData(number=123, timestamp=123, gasLimit=123, gasUsed=100)  # type: ignore
    actual = Block.model_validate(data)
    assert actual.number == 123
