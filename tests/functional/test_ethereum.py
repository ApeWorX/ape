import pytest
from hexbytes import HexBytes

from ape.exceptions import OutOfGasError
from ape_ethereum.transactions import (
    BaseTransaction,
    Receipt,
    TransactionStatusEnum,
    TransactionType,
)


@pytest.mark.parametrize("type_kwarg", (0, "0x0", b"\x00", "0", HexBytes("0x0"), HexBytes("0x00")))
def test_create_static_fee_transaction(ethereum, type_kwarg):
    txn = ethereum.create_transaction(type=type_kwarg)
    assert txn.type == TransactionType.STATIC.value


@pytest.mark.parametrize("type_kwarg", (None, 2, "0x02", b"\x02", "2", "02", HexBytes("0x02")))
def test_create_dynamic_fee_transaction(ethereum, type_kwarg):
    txn = ethereum.create_transaction(type=type_kwarg)
    assert txn.type == TransactionType.DYNAMIC.value


def test_base_transaction_dict_excludes_none_values():
    txn = BaseTransaction(type=0)
    txn.value = 1000000
    actual = txn.dict()
    assert "value" in actual
    txn.value = None
    actual = txn.dict()
    assert "value" not in actual


def test_receipt_raise_for_status_out_of_gas_error(mocker):
    gas_limit = 100000
    receipt = Receipt(
        provider=mocker.MagicMock(),
        txn_hash="",
        gas_used=gas_limit,
        gas_limit=gas_limit,
        status=TransactionStatusEnum.FAILING.value,
        gas_price=0,
        block_number=0,
        sender="",
        receiver="",
        nonce=0,
    )
    with pytest.raises(OutOfGasError):
        receipt.raise_for_status()
