import pytest

from ape.exceptions import OutOfGasError
from ape_ethereum.ecosystem import BaseTransaction, Receipt, TransactionStatusEnum


class TestBaseTransaction:
    def test_dict_excludes_none_values(self):
        txn = BaseTransaction()
        txn.value = 1000000
        actual = txn.dict()
        assert "value" in actual
        txn.value = None
        actual = txn.dict()
        assert "value" not in actual


class TestReceipt:
    def test_raise_for_status_out_of_gas_error(self, mocker):
        gas_limit = 100000
        receipt = Receipt(
            provider=mocker.MagicMock(),
            txn_hash="",
            gas_used=gas_limit,
            gas_limit=gas_limit,
            status=TransactionStatusEnum.FAILING,
            gas_price=0,
            block_number=0,
            sender="",
            receiver="",
            nonce=0,
        )
        with pytest.raises(OutOfGasError):
            receipt.raise_for_status()
