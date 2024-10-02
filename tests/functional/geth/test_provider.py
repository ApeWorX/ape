from pathlib import Path
from typing import cast

import pytest
from eth_pydantic_types import HashBytes32
from eth_typing import HexStr
from eth_utils import keccak, to_hex
from evmchains import PUBLIC_CHAIN_META
from hexbytes import HexBytes
from web3 import AutoProvider, Web3
from web3.exceptions import ContractLogicError as Web3ContractLogicError
from web3.exceptions import ExtraDataLengthError
from web3.middleware import geth_poa_middleware as ExtraDataToPOAMiddleware
from web3.providers import HTTPProvider

from ape.exceptions import (
    APINotImplementedError,
    BlockNotFoundError,
    ContractLogicError,
    NetworkMismatchError,
    ProviderError,
    TransactionError,
    TransactionNotFoundError,
    VirtualMachineError,
)
from ape.utils import to_int
from ape_ethereum.ecosystem import Block
from ape_ethereum.provider import DEFAULT_SETTINGS, EthereumNodeProvider
from ape_ethereum.trace import TraceApproach
from ape_ethereum.transactions import (
    AccessList,
    AccessListTransaction,
    DynamicFeeTransaction,
    TransactionStatusEnum,
    TransactionType,
)
from ape_node.provider import GethDevProcess, Node, NodeSoftwareNotInstalledError
from tests.conftest import GETH_URI, geth_process_test


@pytest.fixture
def web3_factory(mocker):
    return mocker.patch("ape_ethereum.provider._create_web3")


@pytest.fixture
def tx_for_call(geth_contract):
    return DynamicFeeTransaction.model_validate(
        {
            "chainId": 1337,
            "to": geth_contract.address,
            "gas": 4716984,
            "value": 0,
            "data": HexBytes(keccak(text="myNumber()")[:4]),
            "type": 2,
            "accessList": [],
        }
    )


@geth_process_test
def test_uri(geth_provider):
    assert geth_provider.http_uri == GETH_URI
    assert not geth_provider.ws_uri
    assert geth_provider.uri == GETH_URI


@geth_process_test
def test_uri_localhost_not_running_uses_random_default(config):
    cfg = config.get_config("node").ethereum.mainnet
    assert cfg["uri"] in PUBLIC_CHAIN_META["ethereum"]["mainnet"]["rpc"]
    cfg = config.get_config("node").ethereum.sepolia
    assert cfg["uri"] in PUBLIC_CHAIN_META["ethereum"]["sepolia"]["rpc"]


@geth_process_test
def test_uri_when_configured(geth_provider, project, ethereum):
    settings = geth_provider.provider_settings
    geth_provider.provider_settings = {}
    value = "https://value/from/config"
    config = {"node": {"ethereum": {"local": {"uri": value}, "mainnet": {"uri": value}}}}
    expected = DEFAULT_SETTINGS["uri"]
    network = ethereum.get_network("mainnet")

    try:
        with project.temp_config(**config):
            # Assert we use the config value.
            actual_local_uri = geth_provider.uri
            # Assert provider settings takes precedence.
            provider = network.get_provider("node", provider_settings={"uri": expected})
            actual_mainnet_uri = provider.uri

    finally:
        geth_provider.provider_settings = settings

    assert actual_local_uri == value
    assert actual_mainnet_uri == expected


@geth_process_test
def test_uri_non_dev_and_not_configured(mocker, ethereum):
    """
    If the URI was not configured and we are not using a dev
    network (local or -fork), then it should fail, rather than
    use local-host.
    """
    network = ethereum.sepolia.model_copy(deep=True)

    # NOTE: This may fail if using real network names that evmchains would
    #  know about.
    network.name = "gorillanet"
    network.ecosystem.name = "gorillas"

    provider = Node.model_construct(network=network)

    with pytest.raises(ProviderError):
        _ = provider.uri

    # Show that if an evm-chains _does_ exist, it will use that.
    patch = mocker.patch("ape_ethereum.provider.get_random_rpc")

    # The following URL is made up (please keep example.com).
    expected = "https://gorillas.example.com/v1/rpc"
    patch.return_value = "https://gorillas.example.com/v1/rpc"

    actual = provider.uri
    assert actual == expected


@geth_process_test
def test_repr_connected(geth_provider):
    actual = repr(geth_provider)
    expected = f"<Node ({geth_provider.client_version}) chain_id=1337>"
    assert actual == expected


@geth_process_test
def test_repr_on_local_network_and_disconnected(networks):
    node = networks.get_provider_from_choice("ethereum:local:node")
    # Ensure disconnected.
    if w3 := node._web3:
        node._web3 = None

    actual = repr(node)
    expected = "<Node chain_id=1337>"
    assert actual == expected

    if w3:
        node._web3 = w3


@geth_process_test
def test_repr_on_live_network_and_disconnected(networks):
    node = networks.get_provider_from_choice("ethereum:sepolia:node")
    actual = repr(node)
    expected = "<Node chain_id=11155111>"
    assert actual == expected


@geth_process_test
def test_get_logs(geth_contract, geth_account):
    geth_contract.setNumber(101010, sender=geth_account)
    actual = geth_contract.NumberChange[-1]
    assert actual.event_name == "NumberChange"
    assert actual.contract_address == geth_contract.address
    assert actual.event_arguments["newNum"] == 101010


@geth_process_test
def test_chain_id_when_connected(geth_provider):
    assert geth_provider.chain_id == 1337


@geth_process_test
def test_chain_id_live_network_not_connected(networks):
    node = networks.get_provider_from_choice("ethereum:sepolia:node")
    assert node.chain_id == 11155111


@geth_process_test
def test_chain_id_live_network_connected_uses_web3_chain_id(mocker, geth_provider):
    mock_network = mocker.MagicMock()
    mock_network._chain_id = 999999999  # Shouldn't use hardcoded network
    mock_network.name = "mock"
    orig_network = geth_provider.network

    try:
        geth_provider.network = mock_network
        actual = geth_provider.chain_id
    finally:
        geth_provider.network = orig_network

    # Still use the connected chain ID instead network's
    assert actual == 1337


@geth_process_test
def test_connect_wrong_chain_id(ethereum, geth_provider, web3_factory):
    start_network = geth_provider.network
    expected_error_message = (
        f"Provider connected to chain ID '{geth_provider._web3.eth.chain_id}', "
        "which does not match network chain ID '11155111'. "
        "Are you connected to 'sepolia'?"
    )

    try:
        geth_provider.network = ethereum.get_network("sepolia")

        # Ensure when reconnecting, it does not use HTTP
        web3_factory.return_value = geth_provider._web3
        with pytest.raises(NetworkMismatchError, match=expected_error_message):
            geth_provider.connect()
    finally:
        geth_provider.network = start_network


@geth_process_test
def test_connect_to_chain_that_started_poa(mock_web3, web3_factory, ethereum):
    """
    Ensure that when connecting to a chain that
    started out as PoA, such as Sepolia, we include
    the right middleware. Note: even if the chain
    is no longer PoA, we still need the middleware
    to fetch blocks during the PoA portion of the chain.
    """
    mock_web3.eth.get_block.side_effect = ExtraDataLengthError
    mock_web3.eth.chain_id = ethereum.sepolia.chain_id
    web3_factory.return_value = mock_web3
    provider = ethereum.sepolia.get_provider("node")
    provider.provider_settings = {"uri": "http://node.example.com"}  # fake
    provider.connect()

    # Verify PoA middleware was added.
    assert mock_web3.middleware_onion.inject.call_args[0] == (ExtraDataToPOAMiddleware,)
    assert mock_web3.middleware_onion.inject.call_args[1] == {"layer": 0}


@geth_process_test
def test_connect_using_only_ipc_for_uri(project, networks, geth_provider):
    ipc_path = geth_provider.ipc_path
    with project.temp_config(node={"ethereum": {"local": {"uri": f"{ipc_path}"}}}):
        with networks.ethereum.local.use_provider("node") as node:
            assert node.uri == f"{ipc_path}"


@geth_process_test
def test_connect_request_headers(project, geth_provider, networks):
    http_provider = None
    config = {
        "request_headers": {"h0": 0, "User-Agent": "myapp/2.0"},
        "ethereum": {
            "request_headers": {"h1": 1, "User-Agent": "ETH/1.0"},
            "local": {
                "request_headers": {"h2": 2, "user-agent": "MyPrivateNetwork/0.0.1"},
            },
        },
        "node": {"request_headers": {"h3": 3, "USER-AGENT": "custom-geth-client/v100"}},
    }
    with project.temp_config(**config):
        with networks.ethereum.local.use_provider("node") as geth:
            w3_provider = geth.web3.provider
            if isinstance(w3_provider, AutoProvider):
                for pot_provider_fn in w3_provider._potential_providers:
                    pot_provider = pot_provider_fn()
                    if not isinstance(pot_provider, HTTPProvider):
                        continue
                    else:
                        http_provider = pot_provider

            elif isinstance(w3_provider, HTTPProvider):
                http_provider = w3_provider

            else:
                pytest.fail("Not using HTTP. Please adjust test.")

            assert http_provider is not None, "Setup failed - HTTP Provider still None."

            assert isinstance(http_provider._request_kwargs, dict)
            actual = http_provider._request_kwargs["headers"]
            assert actual["h0"] == 0  # top-level
            assert actual["h1"] == 1  # ecosystem
            assert actual["h2"] == 2  # network
            assert actual["h3"] == 3  # provider

            # Also, assert Ape's default user-agent strings.
            assert actual["User-Agent"].startswith("Ape/")
            assert "Python" in actual["User-Agent"]
            assert "ape-ethereum" in actual["User-Agent"]
            assert "web3.py/" in actual["User-Agent"]

            # Show other default headers.
            assert actual["Content-Type"] == "application/json"

            # Show appended user-agents strings.
            assert "myapp/2.0" in actual["User-Agent"]
            assert "ETH/1.0" in actual["User-Agent"]
            assert "MyPrivateNetwork/0.0.1" in actual["User-Agent"]
            assert "custom-geth-client/v100" in actual["User-Agent"]


@geth_process_test
@pytest.mark.parametrize("block_id", (0, "0", "0x0", HexStr("0x0")))
def test_get_block(geth_provider, block_id):
    block = cast(Block, geth_provider.get_block(block_id))

    # Each parameter is the same as requesting the first block.
    assert block.number == 0
    assert block.base_fee == 0
    assert block.gas_used == 0


@geth_process_test
def test_get_block_not_found(geth_provider):
    latest_block = geth_provider.get_block("latest")
    block_id = latest_block.number + 1000
    with pytest.raises(BlockNotFoundError, match=f"Block with ID '{block_id}' not found."):
        geth_provider.get_block(block_id)


@geth_process_test
def test_get_block_pending(geth_provider, geth_account, geth_second_account, accounts):
    """
    Pending timestamps can be weird.
    This ensures we can check those are various strange states of geth.
    """
    actual = geth_provider.get_block("latest")
    assert isinstance(actual, Block)

    snap = geth_provider.snapshot()

    # Transact to increase block
    geth_account.transfer(geth_second_account, "1 gwei")
    actual = geth_provider.get_block("latest")
    assert isinstance(actual, Block)

    # Restore state before transaction
    geth_provider.restore(snap)
    actual = geth_provider.get_block("latest")
    assert isinstance(actual, Block)


@geth_process_test
def test_get_receipt_not_exists_with_timeout(geth_provider):
    txn_hash = "0x0123"
    expected = (
        f"Transaction '{txn_hash}' not found. "
        rf"Error: Transaction '{txn_hash}' "
        "is not in the chain after 0 seconds"
    )
    with pytest.raises(TransactionNotFoundError, match=expected):
        geth_provider.get_receipt(txn_hash, timeout=0)


@geth_process_test
def test_get_receipt(accounts, geth_provider, geth_account, geth_contract):
    receipt = geth_contract.setNumber(111111, sender=geth_account)
    actual = geth_provider.get_receipt(receipt.txn_hash)
    assert receipt.txn_hash == actual.txn_hash
    assert actual.receiver == geth_contract.address
    assert actual.sender == receipt.sender


@geth_process_test
def test_snapshot_and_revert(geth_provider, geth_account, geth_contract):
    snapshot = geth_provider.snapshot()
    start_nonce = geth_account.nonce
    geth_contract.setNumber(211112, sender=geth_account)  # Advance a block
    actual_block_number = geth_provider.get_block("latest").number
    expected_block_number = snapshot + 1
    actual_nonce = geth_account.nonce
    expected_nonce = start_nonce + 1
    assert actual_block_number == expected_block_number
    assert actual_nonce == expected_nonce

    geth_provider.restore(snapshot)

    actual_block_number = geth_provider.get_block("latest").number
    expected_block_number = snapshot
    actual_nonce = geth_account.nonce
    expected_nonce = start_nonce
    assert actual_block_number == expected_block_number
    assert actual_nonce == expected_nonce

    # Use account after revert
    receipt = geth_contract.setNumber(311113, sender=geth_account)  # Advance a block
    assert not receipt.failed


@geth_process_test
def test_return_value_list(geth_account, geth_contract, geth_provider):
    receipt = geth_contract.getFilledArray.transact(sender=geth_account)
    assert receipt.return_value == [1, 2, 3]


@geth_process_test
def test_return_value_nested_address_array(
    geth_account, geth_contract, geth_provider, zero_address
):
    receipt = geth_contract.getNestedAddressArray.transact(sender=geth_account)
    expected = [
        [geth_account.address, geth_account.address, geth_account.address],
        [zero_address, zero_address, zero_address],
    ]
    assert receipt.return_value == expected


@geth_process_test
def test_return_value_nested_struct_in_tuple(geth_account, geth_contract, geth_provider):
    receipt = geth_contract.getNestedStructWithTuple1.transact(sender=geth_account)
    actual = receipt.return_value
    assert actual[0].t.a == geth_account.address
    assert actual[0].foo == 1
    assert actual[1] == 1


@geth_process_test
def test_get_pending_block(geth_provider, geth_account, geth_second_account, accounts):
    """
    Pending timestamps can be weird.
    This ensures we can check those are various strange states of geth.
    """
    actual = geth_provider.get_block("latest")
    assert isinstance(actual, Block)

    snap = geth_provider.snapshot()

    # Transact to increase block
    geth_account.transfer(geth_second_account, "1 gwei")
    actual = geth_provider.get_block("latest")
    assert isinstance(actual, Block)

    # Restore state before transaction
    geth_provider.restore(snap)
    actual = geth_provider.get_block("latest")
    assert isinstance(actual, Block)


@geth_process_test
def test_isolate(chain, geth_contract, geth_account):
    number_at_start = 444
    geth_contract.setNumber(number_at_start, sender=geth_account)
    start_head = chain.blocks.height

    with chain.isolate():
        geth_contract.setNumber(333, sender=geth_account)
        actual = geth_contract.myNumber()
        height = chain.blocks.height

    assert actual == 333
    assert height == start_head + 1
    assert geth_contract.myNumber() == number_at_start

    # Allow extra 1 to account for potential parallelism-related discrepancy
    assert chain.blocks.height in (start_head, start_head + 1)


@geth_process_test
def test_gas_price(geth_provider):
    actual = geth_provider.gas_price
    assert isinstance(actual, int)


@geth_process_test
def test_send_transaction_when_no_error_and_receipt_fails(
    mock_transaction,
    mock_web3,
    geth_provider,
    owner,
    geth_contract,
):
    start_web3 = geth_provider._web3
    geth_provider._web3 = mock_web3
    # Getting a receipt "works", but you get a failed one.
    # NOTE: Value is meaningless.
    tx_hash = HashBytes32.__eth_pydantic_validate__(123**36)
    receipt_data = {
        "failed": True,
        "blockNumber": 0,
        "txnHash": to_hex(tx_hash),
        "status": TransactionStatusEnum.FAILING.value,
        "sender": owner.address,
        "receiver": geth_contract.address,
        "input": b"",
        "gasUsed": 123,
        "gasLimit": 100,
    }

    try:
        # Sending tx "works" meaning no vm error.
        mock_web3.eth.send_raw_transaction.return_value = tx_hash
        mock_web3.eth.wait_for_transaction_receipt.return_value = receipt_data

        # Attempting to replay the tx does not produce any error.
        mock_web3.eth.call.return_value = HexBytes("")

        # Execute test.
        with pytest.raises(TransactionError):
            geth_provider.send_transaction(mock_transaction)

    finally:
        geth_provider._web3 = start_web3


@geth_process_test
def test_send_call(geth_provider, ethereum, tx_for_call):
    actual = geth_provider.send_call(tx_for_call)
    assert to_int(actual) == 0


@geth_process_test
def test_send_call_base_class_block_id(networks, ethereum, mocker):
    """
    Testing a case where was a bug in the base class for most providers.
    Note: can't use ape-node as-is, as it overrides `send_call()`.
    """

    provider = mocker.MagicMock()
    provider.network.name = "mainnet"

    def hacked_send_call(*args, **kwargs):
        return EthereumNodeProvider.send_call(provider, *args, **kwargs)

    provider.send_call = hacked_send_call
    tx = ethereum.create_transaction()
    block_id = 567

    orig = networks.active_provider
    networks.active_provider = provider
    _ = provider.send_call(tx, block_id=block_id, skip_trace=True) == HexStr("0x")
    networks.active_provider = orig  # put back ASAP

    actual = provider._prepare_call.call_args[-1]["block_identifier"]
    assert actual == block_id


@geth_process_test
def test_send_call_handles_contract_type_failure(mocker, geth_provider, tx_for_call, mock_web3):
    """
    Fixes an issue where we would get a recursion error during
    handling a CALL failure, which would happen during proxy detection.
    """
    orig_web3 = geth_provider._web3

    def sfx(rpc, arguments, *args, **kwargs):
        if rpc == "eth_call" and arguments[0]:
            raise ContractLogicError()

        return orig_web3.provider.make_request(rpc, arguments, *args, **kwargs)

    # Do this to trigger re-entrancy.
    mock_get = mocker.MagicMock()
    mock_get.side_effect = RecursionError
    orig = geth_provider.chain_manager.contracts.get
    geth_provider.chain_manager.contracts.get = mock_get

    mock_web3.provider.make_request.side_effect = sfx
    geth_provider._web3 = mock_web3
    try:
        with pytest.raises(VirtualMachineError):
            geth_provider.send_call(tx_for_call)
    finally:
        geth_provider._web3 = orig_web3
        geth_provider.chain_manager.contracts.get = orig


@geth_process_test
def test_send_call_skip_trace(mocker, geth_provider, ethereum, tx_for_call):
    """
    When we pass skip_trace=True to `send_call` (as proxy-checking des), we should
    also not bother with any traces in exception handling for that call, as proxy-
    checks fail consistently and getting their traces is unnecessary.
    """
    eth_call_spy = mocker.spy(geth_provider, "_eth_call")
    get_contract_spy = mocker.spy(geth_provider.chain_manager.contracts, "get")
    geth_provider.send_call(tx_for_call, skip_trace=True)
    assert eth_call_spy.call_args[1]["skip_trace"] is True
    assert get_contract_spy.call_count == 0


@geth_process_test
def test_network_choice(geth_provider):
    actual = geth_provider.network_choice
    expected = "ethereum:local:node"
    assert actual == expected


@geth_process_test
def test_network_choice_when_custom(geth_provider):
    name = geth_provider.network.name
    geth_provider.network.name = "custom"
    try:
        actual = geth_provider.network_choice
    finally:
        geth_provider.network.name = name

    assert actual == "http://127.0.0.1:5550"


@geth_process_test
def test_make_request_not_exists(geth_provider):
    with pytest.raises(
        APINotImplementedError,
        match="RPC method 'ape_thisDoesNotExist' is not implemented by this node instance.",
    ):
        geth_provider.make_request("ape_thisDoesNotExist")


@geth_process_test
@pytest.mark.parametrize(
    "message",
    (
        "ape_thisDoesNotExist does not exist/is not available",
        "method not found",
        "Method ape_thisDoesNotExist not found",
        "Unknown RPC Endpoint ape_thisDoesNotExist",
    ),
)
def test_make_request_not_exists_different_messages(message, mock_web3, geth_provider):
    def mock_make_request(*args, **kwargs):
        return {"error": message}

    mock_web3.provider.make_request.side_effect = mock_make_request

    class MyProvider(EthereumNodeProvider):
        @property
        def web3(self) -> Web3:
            return mock_web3

    provider = MyProvider(network=geth_provider.network)
    with pytest.raises(
        APINotImplementedError,
        match="RPC method 'ape_thisDoesNotExist' is not implemented by this node instance.",
    ):
        provider.make_request("ape_thisDoesNotExist")


@geth_process_test
def test_geth_bin_not_found():
    bin_name = "__NOT_A_REAL_EXECUTABLE_HOPEFULLY__"
    with pytest.raises(NodeSoftwareNotInstalledError):
        _ = GethDevProcess(Path.cwd(), executable=bin_name)


@geth_process_test
def test_base_fee(geth_provider, mocker):
    # NOTE: Only mocked to guarantee we are in a state
    #   with history.
    orig = geth_provider._web3.eth.fee_history
    mock_fee_history = mocker.MagicMock()
    expected = 222
    mock_fee_history.return_value = {"baseFeePerGas": [111, expected]}
    geth_provider._web3.eth.fee_history = mock_fee_history

    try:
        actual = geth_provider.base_fee
    finally:
        geth_provider._web3.eth.fee_history = orig

    assert actual == expected


@geth_process_test
@pytest.mark.parametrize("ret", [{}, {"baseFeePerGas": None}, {"baseFeePerGas": []}])
def test_base_fee_no_history(geth_provider, mocker, ret):
    orig = geth_provider._web3.eth.fee_history
    mock_fee_history = mocker.MagicMock()
    mock_fee_history.return_value = ret
    expected = geth_provider._get_last_base_fee()
    geth_provider._web3.eth.fee_history = mock_fee_history

    try:
        actual = geth_provider.base_fee
    finally:
        geth_provider._web3.eth.fee_history = orig

    assert actual == expected


@geth_process_test
def test_base_fee_hex_decode(geth_provider, mocker):
    orig = geth_provider._web3.eth.fee_history
    mock_fee_history = mocker.MagicMock()
    mock_fee_history.return_value = {"baseFeePerGas": ["0x6", "0x7"]}
    expected = 7
    geth_provider._web3.eth.fee_history = mock_fee_history

    try:
        actual = geth_provider.base_fee
    finally:
        geth_provider._web3.eth.fee_history = orig

    assert actual == expected


@geth_process_test
def test_estimate_gas_cost(geth_contract, geth_provider, geth_account):
    txn = geth_contract.setNumber.as_transaction(900, sender=geth_account)
    estimate = geth_provider.estimate_gas_cost(txn)
    assert estimate > 0


@geth_process_test
def test_estimate_gas_cost_of_static_fee_txn(geth_contract, geth_provider, geth_account):
    txn = geth_contract.setNumber.as_transaction(900, sender=geth_account, type=0)
    estimate = geth_provider.estimate_gas_cost(txn)
    assert estimate > 0


@geth_process_test
def test_estimate_gas_cost_reverts(geth_contract, geth_provider, geth_second_account):
    txn = geth_contract.setNumber.as_transaction(900, sender=geth_second_account, type=0)
    with pytest.raises(ContractLogicError):
        geth_provider.estimate_gas_cost(txn)


@geth_process_test
@pytest.mark.parametrize("tx_type", TransactionType)
def test_prepare_transaction_with_max_gas(tx_type, geth_provider, ethereum, geth_account):
    tx = ethereum.create_transaction(type=tx_type.value, sender=geth_account.address)
    tx.gas_limit = None  # Undo set from validator
    assert tx.gas_limit is None, "Test setup failed - couldn't clear tx gas limit."

    # NOTE: The local network by default uses max_gas.
    actual = geth_provider.prepare_transaction(tx)
    assert actual.gas_limit == geth_provider.max_gas


@geth_process_test
def test_prepare_transaction_access_list_from_rpc(geth_provider, geth_contract, geth_account):
    tx = geth_contract.setNumber.as_transaction(
        123, type=TransactionType.ACCESS_LIST, sender=geth_account.address
    )
    assert isinstance(tx, AccessListTransaction), "Setup failed - should be AccessListTx"
    prepared_tx = geth_provider.prepare_transaction(tx)
    assert isinstance(prepared_tx, AccessListTransaction)
    actual = prepared_tx.access_list
    assert len(actual) > 0
    assert isinstance(actual[0], AccessList)
    assert len(actual[0].storage_keys) > 0


@geth_process_test
def test_create_access_list(geth_provider, geth_contract, geth_account):
    tx = geth_contract.setNumber.as_transaction(123, sender=geth_account, type=1)
    actual = geth_provider.create_access_list(tx)
    assert len(actual) > 0
    assert isinstance(actual[0], AccessList)
    assert len(actual[0].storage_keys) > 0


@geth_process_test
def test_get_virtual_machine_error(geth_provider):
    expected = "__EXPECTED__"
    error = Web3ContractLogicError(f"execution reverted: {expected}", "0x08c379a")
    actual = geth_provider.get_virtual_machine_error(error)
    assert actual.message == expected


@geth_process_test
def test_trace_approach_config(project):
    node_cfg = project.config.node.model_dump(by_alias=True)
    node_cfg["call_trace_approach"] = "geth"
    with project.temp_config(node=node_cfg):
        provider = project.network_manager.ethereum.local.get_provider("node")
        assert provider.call_trace_approach is TraceApproach.GETH_STRUCT_LOG_PARSE


@geth_process_test
def test_start(mocker, convert, project, geth_provider):
    amount = convert("100_000 ETH", int)
    spy = mocker.spy(GethDevProcess, "from_uri")

    with project.temp_config(test={"balance": amount}):
        try:
            geth_provider.start()
        except Exception:
            pass  # Exceptions are fine here.

        actual = spy.call_args[1]["balance"]
        assert actual == amount


@geth_process_test
def test_auto_mine(geth_provider):
    assert geth_provider.auto_mine is True
