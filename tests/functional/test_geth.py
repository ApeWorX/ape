from pathlib import Path

import pytest
from web3.exceptions import ContractLogicError as Web3ContractLogicError

from ape.api.networks import LOCAL_NETWORK_NAME
from ape.exceptions import ContractLogicError, NetworkMismatchError, TransactionError
from ape_geth import GethProvider
from tests.functional.data.python import TRACE_RESPONSE

_TEST_REVERT_REASON = "TEST REVERT REASON."


@pytest.fixture
def trace_response():
    return TRACE_RESPONSE


@pytest.fixture
def mock_network(mock_network_api, ethereum):
    mock_network_api.name = LOCAL_NETWORK_NAME
    mock_network_api.ecosystem = ethereum
    return mock_network_api


@pytest.fixture
def geth_provider(mock_network, mock_web3):
    return create_geth(mock_network, mock_web3)


def create_geth(network, web3):
    provider = GethProvider(
        name="geth",
        network=network,
        provider_settings={},
        data_folder=Path("."),
        request_header="",
    )
    provider._web3 = web3
    return provider


@pytest.fixture
def eth_tester_provider_geth(eth_tester_provider, networks):
    """Geth using eth-tester provider"""
    provider = create_geth(eth_tester_provider.network, eth_tester_provider.web3)
    init_provider = networks.active_provider
    networks.active_provider = provider
    yield provider
    networks.active_provider = init_provider


def test_send_when_web3_error_raises_transaction_error(geth_provider, mock_web3, mock_transaction):
    web3_error_data = {
        "code": -32000,
        "message": "Test Error Message",
    }
    mock_web3.eth.send_raw_transaction.side_effect = ValueError(web3_error_data)
    with pytest.raises(TransactionError) as err:
        geth_provider.send_transaction(mock_transaction)

    assert web3_error_data["message"] in str(err.value)


def test_send_transaction_reverts_from_contract_logic(geth_provider, mock_web3, mock_transaction):
    test_err = Web3ContractLogicError(f"execution reverted: {_TEST_REVERT_REASON}")
    mock_web3.eth.send_raw_transaction.side_effect = test_err

    with pytest.raises(ContractLogicError) as err:
        geth_provider.send_transaction(mock_transaction)

    assert str(err.value) == _TEST_REVERT_REASON


def test_send_transaction_no_revert_message(mock_web3, geth_provider, mock_transaction):
    test_err = Web3ContractLogicError("execution reverted")
    mock_web3.eth.send_raw_transaction.side_effect = test_err

    with pytest.raises(ContractLogicError) as err:
        geth_provider.send_transaction(mock_transaction)

    assert str(err.value) == TransactionError.DEFAULT_MESSAGE


def test_uri_default_value(geth_provider):
    assert geth_provider.uri == "http://localhost:8545"


def test_uri_uses_value_from_config(mock_network, mock_web3, temp_config):
    config = {"geth": {"ethereum": {"local": {"uri": "value/from/config"}}}}
    with temp_config(config):
        provider = create_geth(mock_network, mock_web3)
        assert provider.uri == "value/from/config"


def test_uri_uses_value_from_settings(mock_network, mock_web3, temp_config):
    # The value from the adhoc-settings is valued over the value from the config file.
    config = {"geth": {"ethereum": {"local": {"uri": "value/from/config"}}}}
    with temp_config(config):
        provider = create_geth(mock_network, mock_web3)
        provider.provider_settings["uri"] = "value/from/settings"
        assert provider.uri == "value/from/settings"


def test_get_call_tree_erigon(mock_web3, geth_provider, trace_response):
    mock_web3.clientVersion = "erigon_MOCK"
    mock_web3.provider.make_request.return_value = trace_response
    result = geth_provider.get_call_tree(
        "0x053cba5c12172654d894f66d5670bab6215517a94189a9ffc09bc40a589ec04d"
    )
    assert "CALL: 0xC17f2C69aE2E66FD87367E3260412EEfF637F70E.<0x96d373e5> [1401584 gas]" in repr(
        result
    )


def test_repr_on_local_network_and_disconnected(networks):
    geth = networks.get_provider_from_choice("ethereum:local:geth")
    assert repr(geth) == "<geth>"


def test_repr_on_live_network_and_disconnected(networks):
    geth = networks.get_provider_from_choice("ethereum:rinkeby:geth")
    assert repr(geth) == "<geth chain_id=4>"


def test_repr_connected(mock_web3, geth_provider):
    mock_web3.eth.chain_id = 123
    assert repr(geth_provider) == "<geth chain_id=123>"


def test_get_logs_when_connected_to_geth(vyper_contract_instance, eth_tester_provider_geth, owner):
    vyper_contract_instance.setNumber(123, sender=owner)
    actual = vyper_contract_instance.NumberChange[-1]
    assert actual.event_name == "NumberChange"
    assert actual.contract_address == vyper_contract_instance.address
    assert actual.event_arguments["newNum"] == 123


def test_chain_id_when_connected(eth_tester_provider_geth):
    assert eth_tester_provider_geth.chain_id == 131277322940537


def test_chain_id_live_network_not_connected(networks):
    geth = networks.get_provider_from_choice("ethereum:rinkeby:geth")
    assert geth.chain_id == 4


def test_chain_id_live_network_connected_uses_web3_chain_id(mocker, eth_tester_provider_geth):
    mock_network = mocker.MagicMock()
    mock_network.chain_id = 999999999  # Shouldn't use hardcoded network
    orig_network = eth_tester_provider_geth.network
    eth_tester_provider_geth.network = mock_network

    # Still use the connected chain ID instead network's
    assert eth_tester_provider_geth.chain_id == 131277322940537
    eth_tester_provider_geth.network = orig_network


def test_connect_wrong_chain_id(mocker, ethereum, eth_tester_provider_geth):
    eth_tester_provider_geth.network = ethereum.get_network("kovan")

    # Ensure when reconnecting, it does not use HTTP
    factory = mocker.patch("ape_geth.provider._create_web3")
    factory.return_value = eth_tester_provider_geth._web3

    expected_error_message = (
        "Provider connected to chain ID '131277322940537', "
        "which does not match network chain ID '42'. "
        "Are you connected to 'kovan'?"
    )
    with pytest.raises(NetworkMismatchError, match=expected_error_message):
        eth_tester_provider_geth.connect()


def test_supports_tracing(eth_tester_provider_geth):
    assert eth_tester_provider_geth.supports_tracing
