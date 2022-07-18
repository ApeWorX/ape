from pathlib import Path

import pytest
from web3.exceptions import ContractLogicError as Web3ContractLogicError

from ape.api.networks import LOCAL_NETWORK_NAME
from ape.exceptions import ContractLogicError, TransactionError
from ape_geth import GethProvider

_TEST_REVERT_REASON = "TEST REVERT REASON."


@pytest.fixture
def geth_provider(mock_network_api, mock_web3):
    return create_geth(mock_network_api, mock_web3)


def create_geth(network, web3):
    network.name = LOCAL_NETWORK_NAME
    network.ecosystem.name = "ethereum"
    provider = GethProvider(
        name="geth",
        network=network,
        provider_settings={},
        data_folder=Path("."),
        request_header="",
    )
    provider._web3 = web3
    return provider


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


def test_uri_uses_value_from_config(mock_network_api, mock_web3, temp_config):
    config = {"geth": {"ethereum": {"local": {"uri": "value/from/config"}}}}
    with temp_config(config):
        provider = create_geth(mock_network_api, mock_web3)
        assert provider.uri == "value/from/config"


def test_uri_uses_value_from_settings(mock_network_api, mock_web3, temp_config):
    config = {"geth": {"ethereum": {"local": {"uri": "value/from/config"}}}}
    with temp_config(config):
        provider = create_geth(mock_network_api, mock_web3)
        provider.provider_settings["uri"] = "value/from/settings"
        assert provider.uri == "value/from/settings"
