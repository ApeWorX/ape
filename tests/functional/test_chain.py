import time
from datetime import datetime, timedelta
from queue import Queue

import pytest
from hexbytes import HexBytes

import ape
from ape.api.networks import LOCAL_NETWORK_NAME
from ape.contracts import ContractInstance
from ape.exceptions import APINotImplementedError, ChainError, ConversionError


@pytest.fixture(scope="module", autouse=True)
def connection(networks_connected_to_tester):
    yield


@pytest.fixture
def dummy_live_network(chain):
    chain.provider.network.name = "rinkeby"
    yield
    chain.provider.network.name = LOCAL_NETWORK_NAME


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


def test_set_balance(chain, test_accounts):
    with pytest.raises(APINotImplementedError):
        chain.set_balance(test_accounts[0], "1000 ETH")


def test_instance_at(chain, contract_instance):
    contract = chain.contracts.instance_at(str(contract_instance.address))
    assert contract.contract_type == contract_instance.contract_type


def test_instance_at_unknown_hex_str(chain, contract_instance):
    # Fails when decoding Ethereum address and NOT conversion error.
    with pytest.raises(ValueError):
        chain.contracts.instance_at(
            "0x1402b10CA274cD76C441e16C844223F79D3566De12bb12b0aebFE41aDFAe302"
        )


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


def test_deployments_mapping_cache_location(chain):
    # Arrange / Act
    mapping_location = chain.contracts._deployments_mapping_cache
    split_mapping_location = str(mapping_location).split("/")

    # Assert
    assert split_mapping_location[-1] == "deployments_map.json"
    assert split_mapping_location[-2] == "ethereum"


def test_cache_deployment_mapping_to_disk(
    project_with_contract, chain, owner, remove_disk_writes_deployments
):
    # Arrange

    deployed_contract_0 = owner.deploy(project_with_contract.ApeContract0)
    deployed_contract_1 = owner.deploy(project_with_contract.ApeContract1)
    address_0 = deployed_contract_0.address
    address_1 = deployed_contract_1.address
    contract_type_0 = project_with_contract.ApeContract0.contract_type
    contract_type_1 = project_with_contract.ApeContract1.contract_type
    expected_contract_mapping = {
        "ethereum": {"local": {"ApeContract0": [address_0], "ApeContract1": [address_1]}}
    }

    # Act
    chain.contracts._cache_deployment_mapping_to_disk(address_0, contract_type_0)
    chain.contracts._cache_deployment_mapping_to_disk(address_1, contract_type_1)
    contracts_mapping = chain.contracts._load_deployments_mapping()

    # Assert
    assert contracts_mapping == expected_contract_mapping


def test_get_deployments_local(chain, project_with_contract, owner):
    # Arrange
    chain.contracts._local_deployments_mapping = {}
    chain.contracts._local_contracts = {}
    starting_contracts_list_0 = chain.contracts.get_deployments(project_with_contract.ApeContract0)
    starting_contracts_list_1 = chain.contracts.get_deployments(project_with_contract.ApeContract1)

    deployed_contract_0 = owner.deploy(project_with_contract.ApeContract0)
    deployed_contract_1 = owner.deploy(project_with_contract.ApeContract1)

    # Act
    contracts_list_0 = chain.contracts.get_deployments(project_with_contract.ApeContract0)
    contracts_list_1 = chain.contracts.get_deployments(project_with_contract.ApeContract1)

    # Assert
    for contract_list in (contracts_list_0, contracts_list_1):
        assert type(contract_list[0]) == ContractInstance

    assert (
        deployed_contract_0.address
        == contracts_list_0[len(contracts_list_0) - len(starting_contracts_list_0) - 1].address
    )
    assert (
        deployed_contract_1.address
        == contracts_list_1[len(contracts_list_1) - len(starting_contracts_list_1) - 1].address
    )


def test_get_deployments_live(
    chain, project_with_contract, owner, remove_disk_writes_deployments, dummy_live_network
):
    # Arrange
    deployed_contract_0 = owner.deploy(project_with_contract.ApeContract0, required_confirmations=0)
    deployed_contract_1 = owner.deploy(project_with_contract.ApeContract1, required_confirmations=0)
    deployments_mapping = chain.contracts._load_deployments_mapping()

    # Act
    my_contracts_list_0 = chain.contracts.get_deployments(project_with_contract.ApeContract0)
    my_contracts_list_1 = chain.contracts.get_deployments(project_with_contract.ApeContract1)

    # Assert
    assert (
        deployments_mapping["ethereum"]["rinkeby"]["ApeContract0"][-1]
        == deployed_contract_0.address
    )
    assert my_contracts_list_0[-1].address == deployed_contract_0.address
    assert (
        deployments_mapping["ethereum"]["rinkeby"]["ApeContract1"][-1]
        == deployed_contract_1.address
    )
    assert my_contracts_list_1[-1].address == deployed_contract_1.address


def test_get_multiple_deployments_live(
    chain, project_with_contract, owner, remove_disk_writes_deployments, dummy_live_network
):
    # Arrange
    starting_contracts_list_0 = chain.contracts.get_deployments(project_with_contract.ApeContract0)
    starting_contracts_list_1 = chain.contracts.get_deployments(project_with_contract.ApeContract1)

    initial_deployed_contract_0 = owner.deploy(
        project_with_contract.ApeContract0, required_confirmations=0
    )
    initial_deployed_contract_1 = owner.deploy(
        project_with_contract.ApeContract1, required_confirmations=0
    )
    owner.deploy(project_with_contract.ApeContract0, required_confirmations=0)
    owner.deploy(project_with_contract.ApeContract1, required_confirmations=0)
    final_deployed_contract_0 = owner.deploy(
        project_with_contract.ApeContract0, required_confirmations=0
    )
    final_deployed_contract_1 = owner.deploy(
        project_with_contract.ApeContract1, required_confirmations=0
    )
    deployments_mapping = chain.contracts._load_deployments_mapping()

    # Act
    contracts_list_0 = chain.contracts.get_deployments(project_with_contract.ApeContract0)
    contracts_list_1 = chain.contracts.get_deployments(project_with_contract.ApeContract1)

    # Assert
    assert (
        deployments_mapping["ethereum"]["rinkeby"]["ApeContract0"][0]
        == initial_deployed_contract_0.address
    )
    assert contracts_list_0[-1].address == final_deployed_contract_0.address
    assert len(contracts_list_0) - len(starting_contracts_list_0) == 3
    assert (
        deployments_mapping["ethereum"]["rinkeby"]["ApeContract1"][0]
        == initial_deployed_contract_1.address
    )
    assert contracts_list_1[-1].address == final_deployed_contract_1.address
    assert len(contracts_list_1) - len(starting_contracts_list_1) == 3


def test_contract_cache_mapping_updated_on_many_deployments(owner, project_with_contract, chain):
    # Arrange / Act
    starting_contracts_list = chain.contracts.get_deployments(project_with_contract.ApeContract0)
    initial_deployed_contract = owner.deploy(project_with_contract.ApeContract0)

    owner.deploy(project_with_contract.ApeContract0)
    owner.deploy(project_with_contract.ApeContract0)
    final_deployed_contract = owner.deploy(project_with_contract.ApeContract0)

    my_contracts_list = chain.contracts.get_deployments(project_with_contract.ApeContract0)
    initial_contract_index = len(my_contracts_list) - len(starting_contracts_list) - 4

    # Assert
    assert len(my_contracts_list) - len(starting_contracts_list) == 4
    assert final_deployed_contract.address == my_contracts_list[-1].address
    assert my_contracts_list[initial_contract_index].address == initial_deployed_contract.address


def test_poll_blocks_stop_block_not_in_future(chain_at_block_5):
    bad_stop_block = chain_at_block_5.blocks.height

    with pytest.raises(ValueError) as err:
        _ = [x for x in chain_at_block_5.blocks.poll_blocks(stop_block=bad_stop_block)]

    assert str(err.value) == "'stop' argument must be in the future."


def test_poll_blocks(chain_at_block_5, eth_tester_provider, owner, PollDaemon):
    blocks = Queue(maxsize=3)
    poller = chain_at_block_5.blocks.poll_blocks()

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


def test_poll_blocks_timeout(
    vyper_contract_instance, chain_at_block_5, eth_tester_provider, owner, PollDaemon
):
    poller = chain_at_block_5.blocks.poll_blocks(new_block_timeout=1)

    with pytest.raises(ChainError) as err:
        with PollDaemon("blocks", poller, lambda x: None, lambda: False):
            time.sleep(1.5)

    assert "Timed out waiting for new block (time_waited=1" in str(err.value)


def test_contracts_get_multiple(vyper_contract_instance, solidity_contract_instance, chain):
    contract_map = chain.contracts.get_multiple(
        (vyper_contract_instance.address, solidity_contract_instance.address)
    )
    assert len(contract_map) == 2
    assert contract_map[vyper_contract_instance.address] == vyper_contract_instance.contract_type
    assert (
        contract_map[solidity_contract_instance.address] == solidity_contract_instance.contract_type
    )


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
