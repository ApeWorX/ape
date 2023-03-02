import time
from datetime import datetime, timedelta
from queue import Queue
from typing import List

import pytest
from ethpm_types import ContractType
from hexbytes import HexBytes

import ape
from ape.contracts import ContractInstance
from ape.exceptions import APINotImplementedError, ChainError, ConversionError
from ape_ethereum.transactions import Receipt, TransactionStatusEnum


@pytest.fixture
def contract_0(project_with_contract):
    return project_with_contract.ApeContract0


@pytest.fixture
def contract_1(project_with_contract):
    return project_with_contract.ApeContract1


def test_snapshot_and_restore(chain, sender, receiver, vyper_contract_instance, owner):
    initial_balance = receiver.balance  # Initial balance at block 0.
    blocks_to_mine = 5
    snapshot_ids = []

    # Since this receipt is before the snapshotting, it will be present after restoring
    receipt_to_keep = vyper_contract_instance.setNumber(3, sender=owner)
    start_block = chain.blocks.height

    for i in range(blocks_to_mine):
        snapshot_id = chain.snapshot()
        snapshot_ids.append(snapshot_id)
        chain.mine()

    # Since this receipt is after snapshotting, it will be gone after restoring

    assert chain.blocks[-1].number == start_block + blocks_to_mine
    receipt_to_lose = vyper_contract_instance.setNumber(3, sender=owner)

    # Increase receiver's balance
    account_nonce = sender.nonce
    sender.transfer(receiver, "123 wei")

    # Show that we can also provide the snapshot ID as an argument.
    restore_index = 2
    chain.restore(snapshot_ids[restore_index])
    assert sender.nonce == account_nonce

    assert chain.blocks[-1].number == start_block + restore_index

    # Verify we lost and kept the expected transaction hashes from the account history
    owner_txns = [x.txn_hash for x in chain.history[owner].sessional]
    assert receipt_to_keep.txn_hash in owner_txns
    assert receipt_to_lose.txn_hash not in owner_txns

    # Head back to the start block
    chain.restore(snapshot_ids[0])
    assert chain.blocks[-1].number == start_block
    assert receiver.balance == initial_balance


def test_isolate(chain, vyper_contract_instance, owner):
    number_at_start = 444
    vyper_contract_instance.setNumber(number_at_start, sender=owner)
    start_head = chain.blocks.height

    with chain.isolate():
        vyper_contract_instance.setNumber(333, sender=owner)
        assert vyper_contract_instance.myNumber() == 333
        assert chain.blocks.height == start_head + 1

    assert vyper_contract_instance.myNumber() == number_at_start
    assert chain.blocks.height == start_head


def test_get_receipt_uses_cache(mocker, eth_tester_provider, chain, vyper_contract_instance, owner):
    expected = vyper_contract_instance.setNumber(3, sender=owner)
    eth = eth_tester_provider.web3.eth
    rpc_spy = mocker.spy(eth, "get_transaction")
    actual = chain.get_receipt(expected.txn_hash)
    assert actual.txn_hash == expected.txn_hash
    assert actual.sender == expected.sender
    assert actual.receiver == expected.receiver
    assert not rpc_spy.call_count

    # Show it uses the provider when the receipt is not cached.
    del chain.history._hash_to_receipt_map[expected.txn_hash]
    chain.get_receipt(expected.txn_hash)
    assert rpc_spy.call_count == 1

    # Show it is cached after the first time
    chain.get_receipt(expected.txn_hash)
    assert rpc_spy.call_count == 1  # Not changed


def test_get_receipt_from_history(chain, vyper_contract_instance, owner):
    expected = vyper_contract_instance.setNumber(3, sender=owner)
    actual = chain.history[expected.txn_hash]
    assert actual.txn_hash == expected.txn_hash
    assert actual.sender == expected.sender
    assert actual.receiver == expected.receiver


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
    with pytest.raises(ChainError, match="There are no snapshots to revert to."):
        chain.restore()


def test_history(sender, receiver, chain):
    length_at_start = len(chain.history[sender].sessional)
    receipt = sender.transfer(receiver, "1 wei")
    transactions_from_cache = list(chain.history[sender].sessional)
    assert len(transactions_from_cache) == length_at_start + 1

    txn = transactions_from_cache[-1]
    assert txn.sender == receipt.sender == sender
    assert txn.receiver == receipt.receiver == receiver


def test_history_caches_sender_over_address_key(
    mocker, chain, eth_tester_provider, sender, vyper_contract_container, ethereum
):
    # When getting receipts from the explorer for contracts, it includes transactions
    # made to the contract. This test shows we cache by sender and not address key.
    contract = sender.deploy(vyper_contract_container, 0)
    network = ethereum.local
    txn = ethereum.create_transaction(
        receiver=contract.address, sender=sender.address, value=10000000000000000000000
    )
    known_receipt = Receipt(
        block_number=10,
        gas_price=11,
        gas_used=12,
        gas_limit=13,
        status=TransactionStatusEnum.NO_ERROR.value,
        txn_hash="0x98d2aee8617897b5983314de1d6ff44d1f014b09575b47a88267971beac97b2b",
        transaction=txn,
    )

    # The receipt is already known and cached by the sender.
    chain.history.append(known_receipt)

    # We ask for receipts from the contract, but it returns ones sent to the contract.
    def get_txns_patch(address):
        if address == contract.address:
            yield from [known_receipt]

    mock_explorer = mocker.MagicMock()
    mock_explorer.get_account_transactions.side_effect = get_txns_patch
    network.__dict__["explorer"] = mock_explorer
    eth_tester_provider.network = network

    # Previously, this would error because the receipt was cached with the wrong sender
    actual = [t for t in chain.history[contract.address].sessional]

    # Actual is 0 because the receipt was cached under the sender.
    assert len(actual) == 0


def test_iterate_blocks(chain_that_mined_5):
    blocks = [b for b in chain_that_mined_5.blocks]
    assert len(blocks) >= 5  # Because mined 5 blocks so is at least 5

    iterator = blocks[0].number
    for block in blocks:
        assert block.number == iterator
        iterator += 1


def test_blocks_range(chain_that_mined_5):
    # The number of the block before mining the 5
    start_block = len(chain_that_mined_5.blocks) - 5
    num_to_get = 3  # Expecting blocks [s, s+1, s+2]
    blocks = [b for b in chain_that_mined_5.blocks.range(start_block, start_block + num_to_get)]
    assert len(blocks) == num_to_get

    expected_number = start_block
    prev_block_hash = (
        HexBytes("0x0000000000000000000000000000000000000000000000000000000000000000")
        if start_block == 0
        else chain_that_mined_5.blocks[start_block - 1].hash
    )
    for block in blocks:
        assert block.number == expected_number
        expected_number += 1
        assert block.parent_hash == prev_block_hash
        prev_block_hash = block.hash


def test_blocks_range_too_high_stop(chain_that_mined_5):
    num_blocks = len(chain_that_mined_5.blocks)
    num_blocks_add_1 = num_blocks + 1
    expected = (
        rf"'stop={num_blocks_add_1}' cannot be greater than the chain length \({num_blocks}\)\. "
        rf"Use 'poll_blocks\(\)' to wait for future blocks\."
    )
    with pytest.raises(ChainError, match=expected):
        # Have to run through generator to trigger code in definition.
        list(chain_that_mined_5.blocks.range(num_blocks_add_1))


def test_block_range_with_step(chain_that_mined_5):
    blocks = [b for b in chain_that_mined_5.blocks.range(3, step=2)]
    assert len(blocks) == 2
    assert blocks[0].number == 0
    assert blocks[1].number == 2


def test_block_range_negative_start(chain_that_mined_5):
    with pytest.raises(ValueError) as err:
        _ = [b for b in chain_that_mined_5.blocks.range(-1, 3, step=2)]

    assert "ensure this value is greater than or equal to 0" in str(err.value)


def test_block_range_out_of_order(chain_that_mined_5):
    with pytest.raises(ValueError) as err:
        _ = [b for b in chain_that_mined_5.blocks.range(3, 1, step=2)]

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
    actual = new_timestamp - start_timestamp - 5
    assert actual <= 1


def test_set_pending_timestamp_failure(chain):
    with pytest.raises(
        ValueError, match="Cannot give both `timestamp` and `deltatime` arguments together."
    ):
        chain.mine(
            timestamp=int(datetime.now().timestamp() + timedelta(seconds=10).seconds),
            deltatime=10,
        )


def test_cache_deployment_live_network(
    chain,
    vyper_contract_instance,
    vyper_contract_container,
    remove_disk_writes_deployments,
    dummy_live_network,
):
    # Arrange - Ensure the contract is not cached anywhere
    address = vyper_contract_instance.address
    contract_name = vyper_contract_instance.contract_type.name
    deployments = chain.contracts._deployments
    contract_types = chain.contracts._local_contract_types
    chain.contracts._local_contract_types = {
        a: ct for a, ct in contract_types.items() if a != address
    }
    chain.contracts._deployments = {n: d for n, d in deployments.items() if n != contract_name}

    # Act
    chain.contracts.cache_deployment(vyper_contract_instance)

    # Assert
    actual_deployments = chain.contracts.get_deployments(vyper_contract_container)
    actual_contract_type = chain.contracts._get_contract_type_from_disk(address)
    expected = vyper_contract_instance.contract_type
    assert len(actual_deployments) == 1
    assert actual_deployments[0].address == address
    assert actual_deployments[0].txn_hash == vyper_contract_instance.txn_hash
    assert chain.contracts.get(address) == expected
    assert actual_contract_type == expected


def test_contract_caches_default_contract_type_when_used(solidity_contract_instance, chain, config):
    address = solidity_contract_instance.address
    contract_type = solidity_contract_instance.contract_type

    # Delete contract from local cache if it's there
    if address in chain.contracts._local_contract_types:
        del chain.contracts._local_contract_types[address]

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


def test_set_balance(chain, test_accounts):
    with pytest.raises(APINotImplementedError):
        chain.set_balance(test_accounts[0], "1000 ETH")


def test_instance_at(chain, contract_instance):
    contract = chain.contracts.instance_at(str(contract_instance.address))
    assert contract.contract_type == contract_instance.contract_type


def test_instance_at_unknown_hex_str(chain, contract_instance):
    # Fails when decoding Ethereum address and NOT conversion error.
    hex_str = "0x1402b10CA274cD76C441e16C844223F79D3566De12bb12b0aebFE41aDFAe302"
    with pytest.raises(ValueError, match=f"Unknown address value '{hex_str}'."):
        chain.contracts.instance_at(hex_str)


def test_instance_at_when_given_contract_type(chain, contract_instance):
    contract = chain.contracts.instance_at(
        str(contract_instance.address), contract_type=contract_instance.contract_type
    )
    assert contract.contract_type == contract_instance.contract_type


def test_instance_at_when_given_name_as_contract_type(chain, contract_instance):
    expected_match = "Expected type 'ContractType' for argument 'contract_type'."
    with pytest.raises(TypeError, match=expected_match):
        address = str(contract_instance.address)
        bad_contract_type = contract_instance.contract_type.name
        chain.contracts.instance_at(address, contract_type=bad_contract_type)


def test_instance_at_uses_given_contract_type_when_retrieval_fails(mocker, chain, caplog):
    # The manager always attempts retrieval so that default contact types can
    # get cached. However, sometimes an explorer plugin may fail. If given a contract-type
    # in that situation, we can use it and not fail and log the error instead.
    expected_contract_type = ContractType(contractName="foo", sourceId="foo.bar")
    new_address = "0x4a986a6dCA6dbf99bC3d17F8D71aFb0d60e740f8"
    expected_fail_message = "LOOK_FOR_THIS_FAIL_MESSAGE"
    existing_fn = chain.contracts.get

    def fn(addr, default=None):
        if addr == new_address:
            raise ValueError(expected_fail_message)

        return existing_fn(addr, default=default)

    chain.contracts.get = mocker.MagicMock()
    chain.contracts.get.side_effect = fn

    actual = chain.contracts.instance_at(new_address, contract_type=expected_contract_type)
    assert actual.contract_type == expected_contract_type
    assert caplog.records[-1].message == expected_fail_message


def test_deployments_mapping_cache_location(chain):
    # Arrange / Act
    mapping_location = chain.contracts._deployments_mapping_cache
    split_mapping_location = str(mapping_location).split("/")

    # Assert
    assert split_mapping_location[-1] == "deployments_map.json"
    assert split_mapping_location[-2] == "ethereum"


def test_deployments_when_offline(chain, networks_disconnected, vyper_contract_container):
    """
    Ensure you don't get `ProviderNotConnectedError` here.
    """
    assert chain.contracts.get_deployments(vyper_contract_container) == []


def test_get_deployments_local(chain, owner, contract_0, contract_1):
    # Arrange
    chain.contracts._local_deployments_mapping = {}
    chain.contracts._local_contract_types = {}
    starting_contracts_list_0 = chain.contracts.get_deployments(contract_0)
    starting_contracts_list_1 = chain.contracts.get_deployments(contract_1)
    deployed_contract_0 = owner.deploy(contract_0)
    deployed_contract_1 = owner.deploy(contract_1)

    # Act
    contracts_list_0 = chain.contracts.get_deployments(contract_0)
    contracts_list_1 = chain.contracts.get_deployments(contract_1)

    # Assert
    for contract_list in (contracts_list_0, contracts_list_1):
        assert type(contract_list[0]) == ContractInstance

    index_0 = len(contracts_list_0) - len(starting_contracts_list_0) - 1
    index_1 = len(contracts_list_1) - len(starting_contracts_list_1) - 1
    actual_address_0 = contracts_list_0[index_0].address
    assert actual_address_0 == deployed_contract_0.address
    actual_address_1 = contracts_list_1[index_1].address
    assert actual_address_1 == deployed_contract_1.address


def test_get_deployments_live(
    chain, owner, contract_0, contract_1, remove_disk_writes_deployments, dummy_live_network
):
    deployed_contract_0 = owner.deploy(contract_0, required_confirmations=0)
    deployed_contract_1 = owner.deploy(contract_1, required_confirmations=0)

    # Act
    my_contracts_list_0 = chain.contracts.get_deployments(contract_0)
    my_contracts_list_1 = chain.contracts.get_deployments(contract_1)

    # Assert
    address_from_api_0 = my_contracts_list_0[-1].address
    assert address_from_api_0 == deployed_contract_0.address
    address_from_api_1 = my_contracts_list_1[-1].address
    assert address_from_api_1 == deployed_contract_1.address


def test_get_deployments_live_migration(
    chain, owner, contract_0, dummy_live_network, caplog, use_debug
):
    contract = owner.deploy(contract_0, required_confirmations=0)
    old_style_map = {"ethereum": {"goerli": {"ApeContract0": [contract.address]}}}
    chain.contracts._write_deployments_mapping(old_style_map)
    actual = chain.contracts.get_deployments(contract_0)
    assert actual == [contract]
    assert caplog.records[-1].message == "Migrating 'deployments_map.json'."


def test_get_multiple_deployments_live(
    chain, owner, contract_0, contract_1, remove_disk_writes_deployments, dummy_live_network
):
    starting_contracts_list_0 = chain.contracts.get_deployments(contract_0)
    starting_contracts_list_1 = chain.contracts.get_deployments(contract_1)
    initial_deployed_contract_0 = owner.deploy(contract_0, required_confirmations=0)
    initial_deployed_contract_1 = owner.deploy(contract_1, required_confirmations=0)
    owner.deploy(contract_0, required_confirmations=0)
    owner.deploy(contract_1, required_confirmations=0)
    final_deployed_contract_0 = owner.deploy(contract_0, required_confirmations=0)
    final_deployed_contract_1 = owner.deploy(contract_1, required_confirmations=0)
    contracts_list_0 = chain.contracts.get_deployments(contract_0)
    contracts_list_1 = chain.contracts.get_deployments(contract_1)
    contract_type_map = {
        "ApeContract0": (initial_deployed_contract_0, final_deployed_contract_0),
        "ApeContract1": (initial_deployed_contract_1, final_deployed_contract_1),
    }

    assert len(contracts_list_0) == len(starting_contracts_list_0) + 3
    assert len(contracts_list_1) == len(starting_contracts_list_1) + 3

    for ct_name, ls in zip(("ApeContract0", "ApeContract1"), (contracts_list_0, contracts_list_1)):
        initial_ct, final_ct = contract_type_map[ct_name]
        assert ls[len(ls) - 3].address == initial_ct.address
        assert ls[-1].address == final_ct.address


def test_contract_cache_mapping_updated_on_many_deployments(owner, chain, contract_0, contract_1):
    # Arrange / Act
    initial_contracts = chain.contracts.get_deployments(contract_0)
    expected_first_contract = owner.deploy(contract_0)

    owner.deploy(contract_0)
    owner.deploy(contract_0)
    expected_last_contract = owner.deploy(contract_0)

    actual_contracts = chain.contracts.get_deployments(contract_0)
    first_index = len(initial_contracts)  # next index before deploys from this test
    actual_first_contract = actual_contracts[first_index].address
    actual_last_contract = actual_contracts[-1].address

    # Assert
    fail_msg = f"Check deployments: {', '.join([c.address for c in actual_contracts])}"
    assert len(actual_contracts) - len(initial_contracts) == 4, fail_msg
    assert actual_first_contract == expected_first_contract.address, fail_msg
    assert actual_last_contract == expected_last_contract.address, fail_msg


def test_poll_blocks_stop_block_not_in_future(chain_that_mined_5):
    bad_stop_block = chain_that_mined_5.blocks.height

    with pytest.raises(ValueError, match="'stop' argument must be in the future."):
        _ = [x for x in chain_that_mined_5.blocks.poll_blocks(stop_block=bad_stop_block)]


def test_poll_blocks(chain_that_mined_5, eth_tester_provider, owner, PollDaemon):
    blocks: Queue = Queue(maxsize=3)
    poller = chain_that_mined_5.blocks.poll_blocks()

    with PollDaemon("blocks", poller, blocks.put, blocks.full):
        # Sleep first to ensure listening before mining.
        time.sleep(1)
        eth_tester_provider.mine(3)

    assert blocks.full()
    first = blocks.get().number
    second = blocks.get().number
    third = blocks.get().number
    assert first == second - 1
    assert second == third - 1


def test_poll_blocks_reorg(chain_that_mined_5, eth_tester_provider, owner, PollDaemon, caplog):
    blocks: Queue = Queue(maxsize=6)
    poller = chain_that_mined_5.blocks.poll_blocks()

    with PollDaemon("blocks", poller, blocks.put, blocks.full):
        # Sleep first to ensure listening before mining.
        time.sleep(1)

        snapshot = chain_that_mined_5.snapshot()
        chain_that_mined_5.mine(2)

        # Wait to allow blocks before re-org to get yielded
        time.sleep(5)

        # Simulate re-org by reverting to the snapshot
        chain_that_mined_5.restore(snapshot)

        # Allow it time to trigger realizing there was a re-org
        time.sleep(1)
        chain_that_mined_5.mine(2)
        time.sleep(1)

        chain_that_mined_5.mine(3)

    assert blocks.full()

    # Show that re-org was detected
    expected_error = (
        "Chain has reorganized since returning the last block. "
        "Try adjusting the required network confirmations."
    )
    assert caplog.records, "Didn't detect re-org"
    assert expected_error in caplog.records[-1].message

    # Show that there are duplicate blocks
    block_numbers: List[int] = [blocks.get().number for _ in range(6)]
    assert len(set(block_numbers)) < len(block_numbers)


def test_poll_blocks_timeout(
    vyper_contract_instance, chain_that_mined_5, eth_tester_provider, owner, PollDaemon
):
    poller = chain_that_mined_5.blocks.poll_blocks(new_block_timeout=1)

    with pytest.raises(ChainError, match=r"Timed out waiting for new block \(time_waited=1.\d+\)."):
        with PollDaemon("blocks", poller, lambda x: None, lambda: False):
            time.sleep(1.5)


def test_contracts_get_multiple(vyper_contract_instance, solidity_contract_instance, chain):
    contract_map = chain.contracts.get_multiple(
        (vyper_contract_instance.address, solidity_contract_instance.address)
    )
    assert len(contract_map) == 2
    assert contract_map[vyper_contract_instance.address] == vyper_contract_instance.contract_type
    assert (
        contract_map[solidity_contract_instance.address] == solidity_contract_instance.contract_type
    )


def test_contracts_get_multiple_no_addresses(chain, caplog):
    contract_map = chain.contracts.get_multiple([])
    assert not contract_map
    assert caplog.records[-1].levelname == "WARNING"
    assert "No addresses provided." in caplog.records[-1].message


def test_contracts_get_all_include_non_contract_address(vyper_contract_instance, chain, owner):
    actual = chain.contracts.get_multiple((vyper_contract_instance.address, owner.address))
    assert len(actual) == 1
    assert actual[vyper_contract_instance.address] == vyper_contract_instance.contract_type


def test_contracts_get_multiple_attempts_to_convert(chain):
    with pytest.raises(ConversionError):
        chain.contracts.get_multiple(("test.eth",))


def test_contracts_get_non_contract_address(chain, owner):
    actual = chain.contracts.get(owner.address)
    assert actual is None


def test_contracts_get_attempts_to_convert(chain):
    with pytest.raises(ConversionError):
        chain.contracts.get("test.eth")


def test_cache_non_checksum_address(chain, vyper_contract_instance):
    """
    When caching a non-checksum address, it should use its checksum
    form automatically.
    """
    if vyper_contract_instance.address in chain.contracts:
        del chain.contracts[vyper_contract_instance.address]

    lowered_address = vyper_contract_instance.address.lower()
    chain.contracts[lowered_address] = vyper_contract_instance.contract_type
    assert chain.contracts[vyper_contract_instance.address] == vyper_contract_instance.contract_type
