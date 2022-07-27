import pytest
from eth_typing import HexAddress, HexStr
from hexbytes import HexBytes

from ape.types import AddressType
from ape.utils import DEFAULT_LOCAL_TRANSACTION_ACCEPTANCE_TIMEOUT
from ape_ethereum.ecosystem import Block

LOG = {
    "removed": False,
    "logIndex": "0x0",
    "transactionIndex": "0x0",
    "transactionHash": "0x74dd040dfa06f0af9af8ca95d7aae409978400151c746f55ecce19e7356cfc5a",
    "blockHash": "0x2c99950b07accf3e442512a3352a11e6fed37b2331de5f71b7743b357d96e4e8",
    "blockNumber": "0xa946ac",
    "address": "0x274b028b03a250ca03644e6c578d81f019ee1323",
    "data": "0xabffd4675206dab5d04a6b0d62c975049665d1f512f29f303908abdd20bc08a100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000060000000000000000000000000000000000000000000000000000000000000000744796e616d696300000000000000000000000000000000000000000000000000",  # noqa: E501
    "topics": [
        "0xa84473122c11e32cd505595f246a28418b8ecd6cf819f4e3915363fad1b8f968",
        "0x0000000000000000000000000000000000000000000000000000000000000006",
        "0x9f3d45ac20ccf04b45028b8080bb191eab93e29f7898ed43acf480dd80bba94d",
    ],
}


@pytest.fixture
def event_abi(vyper_contract_instance):
    return vyper_contract_instance.NumberChange.abi


@pytest.mark.parametrize(
    "address",
    (
        "0x63953eB1B3D8DB28334E7C1C69456C851F934199".lower(),
        0x63953EB1B3D8DB28334E7C1C69456C851F934199,
    ),
)
def test_decode_address(ethereum, address):
    expected = "0x63953eB1B3D8DB28334E7C1C69456C851F934199"
    actual = ethereum.decode_address(address)
    assert actual == expected


def test_encode_address(ethereum):
    raw_address = "0x63953eB1B3D8DB28334E7C1C69456C851F934199"
    address = AddressType(HexAddress(HexStr(raw_address)))
    actual = ethereum.encode_address(address)
    assert actual == raw_address


def test_block_handles_snake_case_parent_hash(eth_tester_provider, sender, receiver):
    # Transaction to change parent hash of next block
    sender.transfer(receiver, "1 gwei")

    # Replace 'parentHash' key with 'parent_hash'
    latest_block = eth_tester_provider.get_block("latest")
    latest_block_dict = eth_tester_provider.get_block("latest").dict()
    latest_block_dict["parent_hash"] = latest_block_dict.pop("parentHash")

    redefined_block = Block.parse_obj(latest_block_dict)
    assert redefined_block.parent_hash == latest_block.parent_hash


def test_transaction_acceptance_timeout(temp_config, config, networks):
    assert (
        networks.provider.network.transaction_acceptance_timeout
        == DEFAULT_LOCAL_TRANSACTION_ACCEPTANCE_TIMEOUT
    )
    new_value = DEFAULT_LOCAL_TRANSACTION_ACCEPTANCE_TIMEOUT + 1
    timeout_config = {"ethereum": {"local": {"transaction_acceptance_timeout": new_value}}}
    with temp_config(timeout_config):
        assert networks.provider.network.transaction_acceptance_timeout == new_value


def test_decode_logs(ethereum, vyper_contract_instance):
    abi = vyper_contract_instance.NumberChange.abi
    result = [x for x in ethereum.decode_logs([LOG], abi)]
    assert len(result) == 1
    assert result[0] == {
        "event_name": "NumberChange",
        "contract_address": "0x274b028b03A250cA03644E6c578D81f019eE1323",
        "event_arguments": {
            "newNum": 6,
            "dynIndexed": HexBytes(
                "0x9f3d45ac20ccf04b45028b8080bb191eab93e29f7898ed43acf480dd80bba94d"
            ),
            "b": HexBytes("0xabffd4675206dab5d04a6b0d62c975049665d1f512f29f303908abdd20bc08a1"),
            "prevNum": 0,
            "dynData": "Dynamic",
        },
        "transaction_hash": "0x74dd040dfa06f0af9af8ca95d7aae409978400151c746f55ecce19e7356cfc5a",
        "block_number": 11093676,
        "block_hash": "0x2c99950b07accf3e442512a3352a11e6fed37b2331de5f71b7743b357d96e4e8",
        "log_index": 0,
        "transaction_index": 0,
    }


def test_decode_logs_empty_list(ethereum, event_abi):
    actual = [x for x in ethereum.decode_logs([], event_abi)]
    assert actual == []
