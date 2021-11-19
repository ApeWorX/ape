from pathlib import Path

import pytest
from web3.exceptions import ContractLogicError as Web3ContractLogicError

from ape.api import ReceiptAPI, TransactionStatusEnum
from ape.exceptions import ContractLogicError, TransactionError
from ape_geth import GethProvider

_TEST_REVERT_REASON = "TEST REVERT REASON."


def _create_mock_receipt(status=TransactionStatusEnum.NO_ERROR, gas_used=0):
    class MockReceipt(ReceiptAPI):
        @classmethod
        def decode(cls, data: dict) -> "ReceiptAPI":
            return MockReceipt(
                txn_hash="test-hash",  # type: ignore
                status=status,  # type: ignore
                gas_used=gas_used,  # type: ignore
                gas_price="60000000000",  # type: ignore
                block_number=0,  # type: ignore
            )

    return MockReceipt


class TestEthereumProvider:
    def test_send_when_web3_error_raises_transaction_error(
        self, mock_web3, mock_network_api, mock_config_item, mock_transaction
    ):
        provider = GethProvider(
            name="test",
            network=mock_network_api,
            config=mock_config_item,
            provider_settings={},
            data_folder=Path("."),
            request_header="",
        )
        provider._web3 = mock_web3

        mock_network_api.ecosystem.receipt_class = _create_mock_receipt()
        web3_error_data = {
            "code": -32000,
            "message": "Test Error Message",
        }
        mock_web3.eth.send_raw_transaction.side_effect = ValueError(web3_error_data)
        with pytest.raises(TransactionError) as err:
            provider.send_transaction(mock_transaction)

        assert web3_error_data["message"] in str(err.value)

    def test_send_transaction_reverts_from_contract_logic(
        self, mock_web3, mock_network_api, mock_config_item, mock_transaction
    ):
        provider = GethProvider(
            name="test",
            network=mock_network_api,
            config=mock_config_item,
            provider_settings={},
            data_folder=Path("."),
            request_header="",
        )
        provider._web3 = mock_web3
        mock_network_api.ecosystem.receipt_class = _create_mock_receipt()
        test_err = Web3ContractLogicError(f"execution reverted: {_TEST_REVERT_REASON}")
        mock_web3.eth.send_raw_transaction.side_effect = test_err

        with pytest.raises(ContractLogicError) as err:
            provider.send_transaction(mock_transaction)

        assert str(err.value) == _TEST_REVERT_REASON

    def test_send_transaction_no_revert_message(
        self, mock_web3, mock_network_api, mock_config_item, mock_transaction
    ):
        provider = GethProvider(
            name="test",
            network=mock_network_api,
            config=mock_config_item,
            provider_settings={},
            data_folder=Path("."),
            request_header="",
        )
        provider._web3 = mock_web3
        mock_network_api.ecosystem.receipt_class = _create_mock_receipt()
        test_err = Web3ContractLogicError("execution reverted")
        mock_web3.eth.send_raw_transaction.side_effect = test_err

        with pytest.raises(ContractLogicError) as err:
            provider.send_transaction(mock_transaction)

        assert str(err.value) == TransactionError.DEFAULT_MESSAGE
