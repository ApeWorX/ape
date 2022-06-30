from datetime import datetime, timedelta

import pytest
from hexbytes import HexBytes

import ape
from ape.contracts import ContractInstance
from ape.exceptions import ChainError


@pytest.fixture(scope="module", autouse=True)
def connection(networks_connected_to_tester):
    yield


@pytest.fixture
def chain_at_block_5(chain):
    snapshot_id = chain.snapshot()
    chain.mine(5)
    yield chain
    chain.restore(snapshot_id)


def test_snapshot_and_restore(chain, sender, receiver):
    initial_balance = receiver.balance  # Initial balance at block 0.
    end_range = 5
    snapshot_ids = []

    for i in range(end_range):
        snapshot_id = chain.snapshot()
        snapshot_ids.append(snapshot_id)
        chain.mine()

    assert chain.blocks[-1].number == end_range

    # Increase receiver's balance
    sender.transfer(receiver, "123 wei")

    # Show that we can also provide the snapshot ID as an argument.
    chain.restore(snapshot_ids[2])
    assert chain.blocks[-1].number == 2

    # Head back to the initial block.
    while chain.blocks[-1].number != 0:
        chain.restore()

    assert chain.blocks[-1].number == 0
    assert receiver.balance == initial_balance


def test_snapshot_and_restore_unknown_snapshot_id(chain):
    _ = chain.snapshot()
    chain.mine()
    snapshot_id_2 = chain.snapshot()
    chain.mine()
    snapshot_id_3 = chain.snapshot()
    chain.mine()

    # After restoring to the second ID, the third ID is now invalid.
    chain.restore(snapshot_id_2)

    with pytest.raises(ChainError) as err:
        chain.restore(snapshot_id_3)

    assert "Unknown snapshot ID" in str(err.value)


def test_snapshot_and_restore_no_snapshots(chain):
    chain._snapshots = []  # Ensure empty (gets set in test setup)
    with pytest.raises(ChainError) as err:
        chain.restore("{}")

    assert "There are no snapshots to revert to." in str(err.value)


def test_account_history(sender, receiver, chain):
    assert not chain.account_history[sender]
    receipt = sender.transfer(receiver, "1 wei")
    transactions_from_cache = chain.account_history[sender]
    assert len(transactions_from_cache) == 1

    txn = transactions_from_cache[0]
    assert txn.sender == receipt.sender == sender
    assert txn.receiver == receipt.receiver == receiver


def test_iterate_blocks(chain_at_block_5):
    expected_number_of_blocks = 6  # chain_at_block_5: [0, 1, 2, 3, 4, 5] (len=6)
    blocks = [b for b in chain_at_block_5.blocks]
    assert len(blocks) == expected_number_of_blocks, "Blocks are mined after fixture set"

    expected_number = 0
    for block in blocks:
        assert block.number == expected_number
        expected_number += 1


def test_blocks_range(chain_at_block_5):
    expected_number_of_blocks = 3  # Expecting blocks [0, 1, 2]
    blocks = [b for b in chain_at_block_5.blocks.range(3)]
    assert len(blocks) == expected_number_of_blocks

    expected_number = 0
    prev_block_hash = HexBytes("0x0000000000000000000000000000000000000000000000000000000000000000")
    for block in blocks:
        assert block.number == expected_number
        expected_number += 1
        assert block.parent_hash == prev_block_hash
        prev_block_hash = block.hash


def test_blocks_range_too_high_stop(chain_at_block_5):
    len_plus_1 = len(chain_at_block_5.blocks) + 1
    with pytest.raises(ChainError) as err:
        # Have to run through generator to trigger code in definition.
        _ = [_ for _ in chain_at_block_5.blocks.range(len_plus_1)]

    assert str(err.value) == (
        f"'stop={len_plus_1}' cannot be greater than the chain length (6). "
        f"Use 'poll_blocks()' to wait for future blocks."
    )


def test_block_range_with_step(chain_at_block_5):
    blocks = [b for b in chain_at_block_5.blocks.range(3, step=2)]
    assert len(blocks) == 2
    assert blocks[0].number == 0
    assert blocks[1].number == 2


def test_block_range_negative_start(chain_at_block_5):
    with pytest.raises(ValueError) as err:
        _ = [b for b in chain_at_block_5.blocks.range(-1, 3, step=2)]

    assert "ensure this value is greater than or equal to 0" in str(err.value)


def test_block_range_out_of_order(chain_at_block_5):
    with pytest.raises(ValueError) as err:
        _ = [b for b in chain_at_block_5.blocks.range(3, 1, step=2)]

    assert "stop_block: '0' cannot be less than start_block: '3'." in str(err.value)


def test_set_pending_timestamp(chain):
    start_timestamp = chain.pending_timestamp
    chain.pending_timestamp += 3600
    new_timestamp = chain.pending_timestamp
    assert new_timestamp - start_timestamp == 3600


def test_set_pending_timestamp_with_deltatime(chain):
    start_timestamp = chain.pending_timestamp
    chain.mine(deltatime=5)
    new_timestamp = chain.pending_timestamp
    assert new_timestamp - start_timestamp - 5 <= 1


def test_set_pending_timestamp_failure(chain):
    with pytest.raises(ValueError) as err:
        chain.mine(
            timestamp=int(datetime.now().timestamp() + timedelta(seconds=10).seconds),
            deltatime=10,
        )
    assert str(err.value) == "Cannot give both `timestamp` and `deltatime` arguments together."


def test_contract_caches_default_contract_type_when_used(solidity_contract_instance, chain, config):
    address = solidity_contract_instance.address
    contract_type = solidity_contract_instance.contract_type

    # Delete contract from local cache if it's there
    if address in chain.contracts._local_contracts:
        del chain.contracts._local_contracts[address]

    # Delete cache file if it exists
    cache_file = chain.contracts._contract_types_cache / f"{address}.json"
    if cache_file.is_file():
        cache_file.unlink()

    # Create a contract using the contract type when nothing is cached.
    contract = ape.Contract(address, contract_type=contract_type)
    assert isinstance(contract, ContractInstance)

    # Ensure we don't need the contract type when creating it the second time.
    contract = ape.Contract(address)
    assert isinstance(contract, ContractInstance)


def test_instance_at(chain, contract_instance):
    contract = chain.contracts.instance_at(str(contract_instance.address))
    assert contract.contract_type == contract_instance.contract_type


def test_instance_at_unknown_hex_str(chain, contract_instance):
    # Fails when conversion is attempted. Tests to make sure don't try to convert.
    address = chain.contracts.instance_at(
        "0x1402b10CA274cD76C441e16C844223F79D3566De12bb12b0aebFE41aDFAe302"
    )
    assert not isinstance(address, ContractInstance)


def test_instance_at_when_given_contract_type(chain, contract_instance):
    contract = chain.contracts.instance_at(
        str(contract_instance.address), contract_type=contract_instance.contract_type
    )
    assert contract.contract_type == contract_instance.contract_type


def test_instance_at_when_given_name_as_contract_type(chain, contract_instance):
    with pytest.raises(TypeError) as err:
        chain.contracts.instance_at(
            str(contract_instance.address), contract_type=contract_instance.contract_type.name
        )

    assert str(err.value) == "Expected type 'ContractType' for argument 'contract_type'."
