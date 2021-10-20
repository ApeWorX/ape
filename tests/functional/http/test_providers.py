from pathlib import Path

import pytest
from ape_http import EthereumProvider
from ape_http.providers import _SpecialFailReason, get_tx_error_from_web3_value_error
from web3.exceptions import ContractLogicError

from ape.api import ReceiptAPI, TransactionStatusEnum
from ape.exceptions import VirtualMachineError

_TEST_REVERT_REASON = "TEST REVERT REASON"


@pytest.mark.parametrize(
    "error_dict",
    (
        {"reason": _SpecialFailReason.GAS_OUT_OF_BOUNDS.value, "code": -32000},
        {"reason": _SpecialFailReason.OUT_OF_GAS.value, "code": -32603},
        {"reason": _SpecialFailReason.INSUFFICIENT_FUNDS.value, "code": -32603},
    ),
)
def test_get_tx_error_from_web3_value_error_gas_related(error_dict):
    test_err = ValueError(error_dict)
    actual = get_tx_error_from_web3_value_error(test_err)
    assert type(actual) != VirtualMachineError


def test_get_tx_error_from_web3_value_error_hardhat():
    err_data = {
        "reason": (
            "Error: VM Exception while processing transaction: "
            f"reverted with reason string '{_TEST_REVERT_REASON}'"
        )
    }
    test_err = ValueError(err_data)
    actual = get_tx_error_from_web3_value_error(test_err)
    assert type(actual) == VirtualMachineError


def test_get_tx_error_from_web3_value_error_ganache():
    test_err = ContractLogicError(f"execution reverted: {_TEST_REVERT_REASON}")
    actual = get_tx_error_from_web3_value_error(test_err)
    assert isinstance(actual, VirtualMachineError)
    assert actual.revert_message == _TEST_REVERT_REASON


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
