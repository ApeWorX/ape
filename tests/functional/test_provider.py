import os
from pathlib import Path
from unittest import mock

import pytest
from eth_pydantic_types import HexBytes32
from eth_tester.exceptions import TransactionFailed  # type: ignore
from eth_typing import HexStr
from eth_utils import ValidationError, to_hex
from hexbytes import HexBytes
from requests import HTTPError
from web3.exceptions import ContractPanicError, ExtraDataLengthError, TimeExhausted

from ape import convert
from ape.api.providers import SubprocessProvider
from ape.exceptions import (
    APINotImplementedError,
    BlockNotFoundError,
    ContractLogicError,
    ProviderError,
    TransactionError,
    TransactionNotFoundError,
    UnknownSnapshotError,
)
from ape.types.events import LogFilter
from ape.utils.testing import DEFAULT_TEST_CHAIN_ID
from ape_ethereum.provider import (
    WEB3_PROVIDER_URI_ENV_VAR_NAME,
    EthereumNodeProvider,
    Web3Provider,
    _sanitize_web3_url,
)
from ape_ethereum.transactions import TransactionStatusEnum, TransactionType
from ape_test import LocalProvider


def test_uri(eth_tester_provider):
    assert not eth_tester_provider.http_uri
    assert not eth_tester_provider.ws_uri


@pytest.mark.parametrize("block_id", (0, "0", "0x0", HexStr("0x0")))
def test_get_block(eth_tester_provider, block_id, vyper_contract_instance, owner):
    block = eth_tester_provider.get_block(block_id)

    # Each parameter is the same as requesting the first block.
    assert block.number == 0
    assert block.base_fee == 1000000000
    assert block.gas_used == 0


def test_get_block_not_found(eth_tester_provider):
    latest_block = eth_tester_provider.get_block("latest")
    block_id = latest_block.number + 1000
    with pytest.raises(BlockNotFoundError, match=f"Block with ID '{block_id}' not found."):
        eth_tester_provider.get_block(block_id)


def test_get_block_transaction(vyper_contract_instance, owner, eth_tester_provider):
    # Ensure a transaction in latest block
    receipt = vyper_contract_instance.setNumber(900, sender=owner)
    block = eth_tester_provider.get_block(receipt.block_number)
    assert to_hex(block.transactions[-1].txn_hash) == receipt.txn_hash


def test_estimate_gas(vyper_contract_instance, eth_tester_provider, owner):
    txn = vyper_contract_instance.setNumber.as_transaction(900, sender=owner)
    estimate = eth_tester_provider.estimate_gas_cost(txn)
    assert estimate > 0


def test_estimate_gas_of_static_fee_txn(vyper_contract_instance, eth_tester_provider, owner):
    txn = vyper_contract_instance.setNumber.as_transaction(900, sender=owner, type=0)
    estimate = eth_tester_provider.estimate_gas_cost(txn)
    assert estimate > 0


def test_estimate_gas_with_max_value_from_block(
    mocker, eth_tester_provider, vyper_contract_instance
):
    mock_limit = mocker.patch(
        "ape.api.networks.NetworkAPI.gas_limit", new_callable=mock.PropertyMock
    )
    mock_limit.return_value = "max"
    txn = vyper_contract_instance.setNumber.as_transaction(900)
    gas_cost = eth_tester_provider.estimate_gas_cost(txn)
    latest_block = eth_tester_provider.get_block("latest")

    # NOTE: Gas is estimated if asked, regardless of network defaults.
    assert gas_cost < latest_block.gas_limit


def test_chain_id(eth_tester_provider):
    chain_id = eth_tester_provider.chain_id
    assert chain_id == DEFAULT_TEST_CHAIN_ID


def test_chain_id_is_cached(eth_tester_provider):
    _ = eth_tester_provider.chain_id

    # Unset `_web3` to show that it is not used in a second call to `chain_id`.
    web3 = eth_tester_provider._web3
    eth_tester_provider._web3 = None
    chain_id = eth_tester_provider.chain_id
    assert chain_id == DEFAULT_TEST_CHAIN_ID
    eth_tester_provider._web3 = web3  # Undo


def test_chain_id_from_ethereum_base_provider_is_cached(mock_web3, ethereum, eth_tester_provider):
    """
    Simulated chain ID from a plugin (using base-ethereum class) to ensure is
    also cached.
    """

    def make_request(rpc, arguments):
        if rpc == "eth_chainId":
            return {"result": 11155111}  # Sepolia

        return eth_tester_provider.make_request(rpc, arguments)

    mock_web3.provider.make_request.side_effect = make_request

    class PluginProvider(Web3Provider):
        def connect(self):
            return

        def disconnect(self):
            return

    provider = PluginProvider(name="sim", network=ethereum.sepolia)
    provider._web3 = mock_web3
    assert provider.chain_id == 11155111
    # Unset to web3 to prove it does not check it again (else it would fail).
    provider._web3 = None
    assert provider.chain_id == 11155111


def test_chain_id_when_disconnected(eth_tester_provider):
    expected = DEFAULT_TEST_CHAIN_ID
    eth_tester_provider.disconnect()
    try:
        actual = eth_tester_provider.chain_id
    finally:
        eth_tester_provider.connect()

    assert actual == expected


def test_chain_id_adhoc_http(networks):
    with networks.parse_network_choice("https://www.shibrpc.com") as bor:
        assert bor.chain_id == 109


def test_get_receipt_not_exists_with_timeout(eth_tester_provider):
    unknown_txn = "0x053cba5c12172654d894f66d5670bab6215517a94189a9ffc09bc40a589ec04d"
    expected = (
        f"Transaction '{unknown_txn}' not found. "
        rf"Error: Transaction '{unknown_txn}' "
        "is not in the chain after 0 seconds"
    )
    with pytest.raises(TransactionNotFoundError, match=expected):
        eth_tester_provider.get_receipt(unknown_txn, timeout=0)


def test_get_receipt_exists_with_timeout(eth_tester_provider, vyper_contract_instance, owner):
    receipt_from_invoke = vyper_contract_instance.setNumber(888, sender=owner)
    receipt_from_provider = eth_tester_provider.get_receipt(receipt_from_invoke.txn_hash, timeout=0)
    assert receipt_from_provider.txn_hash == receipt_from_invoke.txn_hash
    assert receipt_from_provider.receiver == vyper_contract_instance.address


def test_get_receipt_ignores_timeout_when_private(
    eth_tester_provider, mock_web3, vyper_contract_instance, owner
):
    receipt_from_invoke = vyper_contract_instance.setNumber(889, sender=owner)
    real_web3 = eth_tester_provider._web3

    mock_web3.eth.wait_for_transaction_receipt.side_effect = TimeExhausted
    eth_tester_provider._web3 = mock_web3
    try:
        receipt_from_provider = eth_tester_provider.get_receipt(
            receipt_from_invoke.txn_hash, timeout=5, private=True
        )

    finally:
        eth_tester_provider._web3 = real_web3

    assert receipt_from_provider.txn_hash == receipt_from_invoke.txn_hash
    assert not receipt_from_provider.confirmed


def test_get_receipt_passes_receipt_when_private(
    eth_tester_provider, mock_web3, vyper_contract_instance, owner
):
    receipt_from_invoke = vyper_contract_instance.setNumber(890, sender=owner)
    real_web3 = eth_tester_provider._web3

    mock_web3.eth.wait_for_transaction_receipt.side_effect = TimeExhausted
    eth_tester_provider._web3 = mock_web3
    try:
        receipt_from_provider = eth_tester_provider.get_receipt(
            receipt_from_invoke.txn_hash,
            timeout=5,
            private=True,
            transaction=receipt_from_invoke.transaction,
        )

    finally:
        eth_tester_provider._web3 = real_web3

    assert receipt_from_provider.txn_hash == receipt_from_invoke.txn_hash
    assert not receipt_from_provider.confirmed

    # Receiver comes from the transaction.
    assert receipt_from_provider.receiver == vyper_contract_instance.address


def test_get_contracts_logs_all_logs(chain, contract_instance, owner, eth_tester_provider):
    start_block = chain.blocks.height
    stop_block = start_block + 100
    log_filter = LogFilter(
        addresses=[contract_instance],
        events=contract_instance.contract_type.events,
        start_block=start_block,
        stop_block=stop_block,
    )
    logs_at_start = len([log for log in eth_tester_provider.get_contract_logs(log_filter)])
    contract_instance.fooAndBar(sender=owner)  # Create 2 logs
    logs_after_new_emit = [log for log in eth_tester_provider.get_contract_logs(log_filter)]
    assert len(logs_after_new_emit) == logs_at_start + 2


def test_get_contract_logs_single_log(chain, contract_instance, owner, eth_tester_provider):
    contract_instance.fooAndBar(sender=owner)  # Create logs
    block = chain.blocks.height
    log_filter = LogFilter.from_event(
        event=contract_instance.FooHappened,
        search_topics={"foo": 0},
        addresses=[contract_instance],
        start_block=block,
        stop_block=block,
    )
    logs = [log for log in eth_tester_provider.get_contract_logs(log_filter)]
    assert len(logs) == 1
    assert logs[0]["foo"] == 0
    assert logs[0].abi == contract_instance.FooHappened.abi

    # Show it looks up the ABI when not cached not anymore.
    logs[0]._abi = None
    assert logs[0].abi == contract_instance.FooHappened.abi

    # Ensure topics are expected.
    topics = logs[0].topics
    expected_topics = [
        "0x1a7c56fae0af54ebae73bc4699b9de9835e7bb86b050dff7e80695b633f17abd",
        "0x0000000000000000000000000000000000000000000000000000000000000000",
    ]
    assert topics == expected_topics


def test_get_contract_logs_single_log_query_multiple_values(
    chain, contract_instance, owner, eth_tester_provider
):
    contract_instance.fooAndBar(sender=owner)  # Create logs
    block = chain.blocks.height
    log_filter = LogFilter.from_event(
        event=contract_instance.FooHappened,
        search_topics={"foo": [0, 1]},
        addresses=[contract_instance],
        start_block=block,
        stop_block=block,
    )
    logs = [log for log in eth_tester_provider.get_contract_logs(log_filter)]
    assert len(logs) >= 1
    assert logs[-1]["foo"] == 0


def test_get_contract_logs_multiple_accounts_for_address(
    chain, contract_instance, owner, eth_tester_provider
):
    """
    Tests the condition when you pass in multiple AddressAPI objects
    during an address-topic search.
    """
    contract_instance.logAddressArray(sender=owner)  # Create logs
    block = chain.blocks.height
    log_filter = LogFilter.from_event(
        event=contract_instance.EventWithAddressArray,
        search_topics={"some_address": [owner, contract_instance]},
        addresses=[contract_instance, owner],
        start_block=block,
        stop_block=block,
    )
    logs = [log for log in eth_tester_provider.get_contract_logs(log_filter)]
    assert len(logs) >= 1
    assert logs[-1]["some_address"] == owner.address


def test_get_contract_logs_single_log_unmatched(
    chain, contract_instance, owner, eth_tester_provider
):
    unmatched_search = {"foo": 2}  # Foo is created with a value of 0
    contract_instance.fooAndBar(sender=owner)  # Create logs
    block = chain.blocks.height
    log_filter = LogFilter.from_event(
        event=contract_instance.FooHappened,
        search_topics=unmatched_search,
        addresses=[contract_instance],
        start_block=block,
        stop_block=block,
    )
    logs = [log for log in eth_tester_provider.get_contract_logs(log_filter)]
    assert len(logs) == 0


def test_supports_tracing(eth_tester_provider):
    assert not eth_tester_provider.supports_tracing


def test_get_balance(networks, accounts):
    balance = networks.provider.get_balance(accounts[0].address)
    assert type(balance) is int
    assert balance > 0


def test_set_timestamp(ethereum):
    # NOTE: Using a different eth-tester for multi-processing ease.
    with ethereum.local.use_provider(
        "test", provider_settings={"chain_id": 919191912828283}
    ) as provider:
        pending_at_start = provider.get_block("pending").timestamp
        new_ts = pending_at_start + 100
        expected = new_ts + 1  # Mining adds another second.
        provider.set_timestamp(new_ts)
        provider.mine()
        actual = provider.get_block("pending").timestamp
        assert actual == expected


def test_set_timestamp_to_same_time(eth_tester_provider):
    """
    Eth tester normally fails when setting the timestamp to the same time.
    However, in Ape, we treat it as a no-op and let it pass.
    """
    expected = eth_tester_provider.get_block("pending").timestamp
    eth_tester_provider.set_timestamp(expected)
    actual = eth_tester_provider.get_block("pending").timestamp
    assert actual == expected


def test_set_timestamp_handle_same_time_race_condition(mocker, eth_tester_provider):
    """
    Ensures that when we get an error saying the timestamps are the same,
    we ignore it and treat it as a noop. This handles the race condition
    when the block advances after ``set_timestamp`` has been called but before
    the operation completes.
    """

    def side_effect(*args, **kwargs):
        raise ValidationError(
            "timestamp must be strictly later than parent, "
            "but is 0 seconds before.\n"
            "- child  : 0\n"
            "- parent : 0."
        )

    mocker.patch.object(eth_tester_provider.evm_backend, "time_travel", side_effect=side_effect)
    eth_tester_provider.set_timestamp(123)


def test_get_virtual_machine_error_when_txn_failed_includes_base_error(
    eth_tester_provider,
):
    txn_failed = TransactionFailed()
    actual = eth_tester_provider.get_virtual_machine_error(txn_failed)
    assert actual.base_err == txn_failed


def test_get_virtual_machine_error_panic(eth_tester_provider, mocker):
    data = "0x4e487b710000000000000000000000000000000000000000000000000000000000000032"
    message = "Panic error 0x32: Array index is out of bounds."
    exception = ContractPanicError(data=data, message=message)
    enrich_spy = mocker.spy(eth_tester_provider.compiler_manager, "enrich_error")
    actual = eth_tester_provider.get_virtual_machine_error(exception)
    assert enrich_spy.call_count == 1
    enrich_spy.assert_called_once_with(actual)
    assert isinstance(actual, ContractLogicError)


def test_gas_price(eth_tester_provider):
    actual = eth_tester_provider.gas_price
    assert isinstance(actual, int)


def test_get_code(eth_tester_provider, vyper_contract_instance):
    address = vyper_contract_instance.address
    block_number = vyper_contract_instance.creation_metadata.block
    assert eth_tester_provider.get_code(address) == eth_tester_provider.get_code(
        address, block_id=block_number
    )


@pytest.mark.parametrize("tx_type", TransactionType)
def test_prepare_transaction_with_max_gas(tx_type, eth_tester_provider, ethereum, owner):
    tx = ethereum.create_transaction(type=tx_type.value, sender=owner.address)
    tx.gas_limit = None  # Undo set from validator
    assert tx.gas_limit is None, "Test setup failed - couldn't clear tx gas limit."

    actual = eth_tester_provider.prepare_transaction(tx)
    assert actual.gas_limit == eth_tester_provider.max_gas
    assert actual.max_fee is not None


def test_no_comma_in_rpc_url():
    test_url = "URI: http://127.0.0.1:8545,"
    sanitised_url = _sanitize_web3_url(test_url)

    assert "," not in sanitised_url


def test_send_transaction_when_no_error_and_receipt_fails(
    mocker,
    mock_web3,
    mock_transaction,
    eth_tester_provider,
    owner,
    vyper_contract_instance,
):
    start_web3 = eth_tester_provider._web3
    eth_tester_provider._web3 = mock_web3
    mock_eth_tester = mocker.MagicMock()
    original_tester = eth_tester_provider.tester
    eth_tester_provider.__dict__["tester"] = mock_eth_tester

    try:
        # NOTE: Value is meaningless.
        tx_hash = HexBytes32.__eth_pydantic_validate__(123**36)

        # Sending tx "works" meaning no vm error.
        mock_eth_tester.ethereum_tester.send_raw_transaction.return_value = tx_hash

        # Getting a receipt "works", but you get a failed one.
        receipt_data = {
            "failed": True,
            "blockNumber": 0,
            "txnHash": to_hex(tx_hash),
            "status": TransactionStatusEnum.FAILING.value,
            "sender": owner.address,
            "receiver": vyper_contract_instance.address,
            "input": b"",
            "gasUsed": 123,
            "gasLimit": 100,
        }
        mock_web3.eth.wait_for_transaction_receipt.return_value = receipt_data

        # Attempting to replay the tx does not produce any error.
        mock_web3.eth.call.return_value = HexBytes("")

        # Execute test.
        mock_transaction.serialize_transaction.return_value = HexBytes(123123123123)
        with pytest.raises(TransactionError):
            eth_tester_provider.send_transaction(mock_transaction)

    finally:
        eth_tester_provider._web3 = start_web3
        eth_tester_provider.__dict__["tester"] = original_tester


def test_network_choice(eth_tester_provider):
    actual = eth_tester_provider.network_choice
    expected = "ethereum:local:test"
    assert actual == expected


def test_network_choice_when_custom(eth_tester_provider):
    name = eth_tester_provider.network.name
    eth_tester_provider.network.name = "custom"
    try:
        # NOTE: Raises this error because EthTester does not support custom
        #   connections.
        with pytest.raises(
            ProviderError, match=".*Custom network provider missing `connection_str`.*"
        ):
            _ = eth_tester_provider.network_choice
    finally:
        eth_tester_provider.network.name = name


def test_make_request_not_exists(eth_tester_provider):
    with pytest.raises(
        APINotImplementedError,
        match="RPC method 'ape_thisDoesNotExist' is not implemented by this node instance.",
    ):
        eth_tester_provider.make_request("ape_thisDoesNotExist")


@pytest.mark.parametrize("msg", ("Method not found", "Method ape_thisDoesNotExist not found"))
def test_make_request_not_exists_dev_nodes(eth_tester_provider, mock_web3, msg):
    """
    Handle an issue found from Base-sepolia where not-implemented RPCs
    caused HTTPErrors.
    """
    real_web3 = eth_tester_provider._web3
    mock_web3.eth = real_web3.eth

    def custom_make_request(rpc, params):
        if rpc == "ape_thisDoesNotExist":
            return {"error": {"message": msg}}

        return real_web3.provider.make_request(rpc, params)

    mock_web3.provider.make_request.side_effect = custom_make_request

    eth_tester_provider._web3 = mock_web3
    try:
        with pytest.raises(
            APINotImplementedError,
            match="RPC method 'ape_thisDoesNotExist' is not implemented by this node instance.",
        ):
            eth_tester_provider.make_request("ape_thisDoesNotExist")
    finally:
        eth_tester_provider._web3 = real_web3


def test_make_request_handles_http_error_method_not_allowed(eth_tester_provider, mock_web3):
    """
    Simulate what *most* of the dev providers do, like hardhat, anvil, and ganache.
    """
    real_web3 = eth_tester_provider._web3
    mock_web3.eth = real_web3.eth

    def custom_make_request(rpc, params):
        if rpc == "ape_thisDoesNotExist":
            raise HTTPError("Client error: Method Not Allowed")

        return real_web3.provider.make_request(rpc, params)

    mock_web3.provider.make_request.side_effect = custom_make_request
    eth_tester_provider._web3 = mock_web3
    try:
        with pytest.raises(
            APINotImplementedError,
            match="RPC method 'ape_thisDoesNotExist' is not implemented by this node instance.",
        ):
            eth_tester_provider.make_request("ape_thisDoesNotExist")
    finally:
        eth_tester_provider._web3 = real_web3


def test_make_request_rate_limiting(mocker, ethereum, mock_web3):
    provider = EthereumNodeProvider(network=ethereum.local)
    provider._web3 = mock_web3

    class RateLimitTester:
        tries = 3
        _try = 0
        tries_made = 0

        def rate_limit_hook(self, rpc, params):
            self.tries_made += 1
            if self._try >= self.tries:
                self._try = 0
                return {"success": True}
            else:
                self._try += 1
                response = mocker.MagicMock()
                response.status_code = 429
                raise HTTPError(response=response)

    rate_limit_tester = RateLimitTester()
    mock_web3.provider.make_request.side_effect = rate_limit_tester.rate_limit_hook
    result = provider.make_request("ape_testRateLimiting", parameters=[])
    assert rate_limit_tester.tries_made == rate_limit_tester.tries + 1
    assert result == {"success": True}


def test_base_fee(eth_tester_provider):
    actual = eth_tester_provider.base_fee
    assert actual >= eth_tester_provider.get_block("pending").base_fee

    # NOTE: Mostly doing this to ensure we are calling the fee history
    #   RPC correctly. There was a bug where we were not.
    actual = eth_tester_provider._get_fee_history(0)
    assert "baseFeePerGas" in actual


def test_has_poa_history_block_data(mock_web3, ethereum, eth_tester_provider):
    class PluginProvider(EthereumNodeProvider):
        pass

    provider = PluginProvider(name="prov", network=ethereum.sepolia)
    provider._web3 = mock_web3

    key = "proofOfAuthorityData"
    mock_web3.eth.get_block.return_value = {key: 123}

    assert provider.has_poa_history


def test_has_poa_history_block_exception(mock_web3, ethereum, eth_tester_provider):
    class PluginProvider(EthereumNodeProvider):
        pass

    provider = PluginProvider(name="prov", network=ethereum.sepolia)
    provider._web3 = mock_web3
    mock_web3.eth.get_block.side_effect = ExtraDataLengthError
    assert provider.has_poa_history


def test_has_poa_history_checks_earliest_and_latest_block(mock_web3, ethereum, eth_tester_provider):
    class PluginProvider(EthereumNodeProvider):
        pass

    provider = PluginProvider(name="prov", network=ethereum.sepolia)
    provider._web3 = mock_web3

    def get_block_side_effect(block_id):
        if block_id == "earliest":
            return {"blockNumber": 0}
        elif block_id == "latest":
            return {"blockNumber": 1, "proofOfAuthorityData": 123}

    mock_web3.eth.get_block.side_effect = get_block_side_effect
    poa_detected = provider.has_poa_history
    assert mock_web3.eth.get_block.call_count == 2
    assert poa_detected


def test_has_poa_history_false(mock_web3, ethereum, eth_tester_provider):
    class PluginProvider(EthereumNodeProvider):
        pass

    provider = PluginProvider(name="prov", network=ethereum.sepolia)
    provider._web3 = mock_web3
    mock_web3.eth.get_block.return_value = {}
    assert not provider.has_poa_history


def test_create_access_list(eth_tester_provider, vyper_contract_instance, owner):
    tx = vyper_contract_instance.setNumber.as_transaction(123, sender=owner)
    with pytest.raises(APINotImplementedError):
        eth_tester_provider.create_access_list(tx)


def test_auto_mine(eth_tester_provider, owner):
    eth_tester_provider.auto_mine = False
    assert not eth_tester_provider.auto_mine

    block_before = eth_tester_provider.get_block("latest").number
    nonce_before = owner.nonce

    # NOTE: Before, this would wait until it timed out, because
    #  when auto mine is off, `ape-test` provider still waited
    #  for the receipt during send_transaction(). It should
    #  instead return early.
    tx = owner.transfer(owner, 123)
    assert not tx.confirmed
    assert tx.sender == owner.address
    assert tx.txn_hash is not None

    nonce_after_tx = owner.nonce
    block_after_tx = eth_tester_provider.get_block("latest").number
    assert nonce_before == nonce_after_tx, "Transaction should not have been mined."
    assert block_before == block_after_tx, "Block height should not have increased."

    eth_tester_provider.mine()
    block_after_mine = eth_tester_provider.get_block("latest").number
    assert block_after_mine > block_after_tx

    eth_tester_provider.auto_mine = True
    assert eth_tester_provider.auto_mine


def test_new_when_web3_provider_uri_set():
    """
    Tests against a confusing case where having an env var
    $WEB3_PROVIDER_URI caused web3.py to only ever use that RPC
    URL regardless of what was said in Ape's --network or config.
    Now, we raise an error to avoid having users think Ape's
    network system is broken.
    """
    os.environ[WEB3_PROVIDER_URI_ENV_VAR_NAME] = "TEST"
    expected = (
        rf"Ape does not support Web3\.py's environment variable "
        rf"\${WEB3_PROVIDER_URI_ENV_VAR_NAME}\. If you are using this environment "
        r"variable name incidentally, please use a different name\. If you are "
        r"trying to set the network in Web3\.py, please use Ape's `ape-config\.yaml` "
        r"or `--network` option instead\."
    )

    class MyProvider(Web3Provider):
        def connect(self):
            raise NotImplementedError()

        def disconnect(self):
            raise NotImplementedError()

    try:
        with pytest.raises(ProviderError, match=expected):
            _ = MyProvider(data_folder=None, name=None, network=None)

    finally:
        if WEB3_PROVIDER_URI_ENV_VAR_NAME in os.environ:
            del os.environ[WEB3_PROVIDER_URI_ENV_VAR_NAME]


def test_account_balance_state(project, eth_tester_provider, owner):
    amount = convert("100_000 ETH", int)

    with project.temp_config(test={"balance": amount}):
        # NOTE: Purposely using a different instance of the provider
        #   for better testing isolation.
        provider = LocalProvider(
            name="test",
            network=eth_tester_provider.network,
        )
        provider.connect()
        bal = provider.get_balance(owner.address)
        assert bal == amount


@pytest.mark.parametrize(
    "uri,key",
    [
        ("ws://example.com", "ws_uri"),
        ("wss://example.com", "ws_uri"),
        ("wss://example.com", "uri"),
    ],
)
def test_node_ws_uri(project, uri, key):
    node = project.network_manager.ethereum.sepolia.get_provider("node")
    assert node.ws_uri is None
    config = {"ethereum": {"sepolia": {key: uri}}}
    with project.temp_config(node=config):
        node = project.network_manager.ethereum.sepolia.get_provider("node")
        assert node.ws_uri == uri

        if key != "ws_uri":
            assert node.uri == uri
        # else: uri gets to set to random HTTP from default settings,
        # but we may want to change that behavior.
        # TODO: 0.9 investigate not using random if ws set.


@pytest.mark.parametrize("http_key", ("uri", "http_uri"))
def test_node_http_uri_with_ws_uri(project, http_key):
    http = "http://example.com"
    ws = "ws://example.com"
    # Showing `uri:` as an HTTP and `ws_uri`: as an additional ws.
    with project.temp_config(node={"ethereum": {"sepolia": {http_key: http, "ws_uri": ws}}}):
        node = project.network_manager.ethereum.sepolia.get_provider("node")
        assert node.uri == http
        assert node.http_uri == http
        assert node.ws_uri == ws


@pytest.mark.parametrize("key", ("uri", "ipc_path"))
def test_ipc_per_network(project, key):
    ipc = "path/to/example.ipc"
    with project.temp_config(node={"ethereum": {"sepolia": {key: ipc}}}):
        node = project.network_manager.ethereum.sepolia.get_provider("node")
        assert node.ipc_path == Path(ipc)
        if key == "uri":
            assert node.uri == ipc
        # else: uri ends up as a random HTTP URI from evmchains.
        # TODO: Do we want to change this in 0.9?


def test_snapshot(eth_tester_provider):
    snapshot = eth_tester_provider.snapshot()
    assert snapshot


def test_restore(eth_tester_provider, accounts):
    account = accounts[0]
    start_nonce = account.nonce
    snapshot = eth_tester_provider.snapshot()
    account.transfer(account, 0)
    eth_tester_provider.restore(snapshot)
    assert account.nonce == start_nonce


def test_restore_zero(eth_tester_provider):
    with pytest.raises(UnknownSnapshotError, match="Unknown snapshot ID '0'."):
        eth_tester_provider.restore(0)


def test_update_settings_invalidates_snapshots(eth_tester_provider, chain):
    snapshot = chain.snapshot()
    assert snapshot in chain._snapshots[eth_tester_provider.chain_id]
    eth_tester_provider.update_settings({})
    assert snapshot not in chain._snapshots[eth_tester_provider.chain_id]


def test_connect_uses_cached_chain_id(mocker, mock_web3, ethereum, eth_tester_provider):
    class PluginProvider(EthereumNodeProvider):
        pass

    web3_factory_patch = mocker.patch("ape_ethereum.provider._create_web3")
    web3_factory_patch.return_value = mock_web3

    class ChainIDTracker:
        call_count = 0

        def make_request(self, rpc, args):
            if rpc == "eth_chainId":
                self.call_count += 1
                return {"result": "0xaa36a7"}  # Sepolia

            return eth_tester_provider.make_request(rpc, args)

    chain_id_tracker = ChainIDTracker()
    mock_web3.provider.make_request.side_effect = chain_id_tracker.make_request

    provider = PluginProvider(name="node", network=ethereum.sepolia)
    provider.connect()
    assert chain_id_tracker.call_count == 1
    provider.disconnect()
    provider.connect()
    # It is still cached from the previous connection.
    assert chain_id_tracker.call_count == 1


class TestSubprocessProvider:
    FAKE_PID = 12345678901234567890

    @pytest.fixture(autouse=True)
    def mock_process(self, mocker):
        mock_process = mocker.MagicMock()
        mock_process.pid = self.FAKE_PID
        return mock_process

    @pytest.fixture(autouse=True)
    def popen_patch(self, mocker, mock_process):
        # Prevent actually creating new processes.
        patch = mocker.patch("ape.api.providers.popen")
        patch.return_value = mock_process
        return patch

    @pytest.fixture(autouse=True)
    def spawn_patch(self, mocker):
        # Prevent spawning process monitoring threads.
        return mocker.patch("ape.api.providers.spawn")

    @pytest.fixture
    def subprocess_provider(self, popen_patch, eth_tester_provider):
        class MockSubprocessProvider(SubprocessProvider):
            @property
            def is_connected(self):
                # Once Popen is called once, we are "connected"
                return popen_patch.call_count > 0

            def build_command(self) -> list[str]:
                return ["apemockprocess"]

        # Hack to allow abstract methods anyway.
        MockSubprocessProvider.__abstractmethods__ = set()  # type: ignore

        return MockSubprocessProvider(name="apemockprocess", network=eth_tester_provider.network)  # type: ignore

    def test_start(self, subprocess_provider):
        assert not subprocess_provider.is_connected
        subprocess_provider.start()
        assert subprocess_provider.is_connected

        # Show it gets tracked in network manager's managed nodes.
        assert self.FAKE_PID in subprocess_provider.network_manager.running_nodes

    def test_start_allow_start_false(self, subprocess_provider):
        subprocess_provider.allow_start = False
        expected = r"Process not started and cannot connect to existing process\."
        with pytest.raises(ProviderError, match=expected):
            subprocess_provider.start()
