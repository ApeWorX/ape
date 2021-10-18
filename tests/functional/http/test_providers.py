from pathlib import Path

import pytest
from ape_http import EthereumProvider

from ape.api import ReceiptAPI, TransactionStatusEnum
from ape.exceptions import VirtualMachineError


class TestEthereumProvider:
    def test_send_when_web3_error_raises_transaction_error(
        self, mock_web3, mock_network_api, mock_config_item, mock_transaction
    ):
        provider = EthereumProvider(
            name="test",
            network=mock_network_api,
            config=mock_config_item,
            provider_settings={},
            data_folder=Path("."),
            request_header="",
        )
        provider._web3 = mock_web3

        class MockReceipt(ReceiptAPI):
            @classmethod
            def decode(cls, data: dict) -> "ReceiptAPI":
                return MockReceipt(
                    txn_hash="test-hash",  # type: ignore
                    status=TransactionStatusEnum.NO_ERROR,  # type: ignore
                    gas_used=0,  # type: ignore
                    gas_price="60000000000",  # type: ignore
                    block_number=0,  # type: ignore
                )

        mock_network_api.ecosystem.receipt_class = MockReceipt
        web3_error_data = {
            "code": -32000,
            "message": "Unable to perform actual",
        }
        mock_web3.eth.send_raw_transaction.side_effect = ValueError(web3_error_data)
        with pytest.raises(VirtualMachineError) as err:
            provider.send_transaction(mock_transaction)

        assert web3_error_data["message"] in str(err.value)
