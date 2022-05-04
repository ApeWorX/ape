import pytest
from eth_typing import HexAddress, HexStr
from hexbytes import HexBytes

from ape.exceptions import OutOfGasError
from ape.types import AddressType
from ape_ethereum.transactions import (
    Receipt,
    StaticFeeTransaction,
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


@pytest.mark.parametrize(
    "address",
    (
        "0x63953eB1B3D8DB28334E7C1C69456C851F934199".lower(),
        0x63953EB1B3D8DB28334E7C1C69456C851F934199,
    ),
)
def test_decode_address(ethereum, address):
    expected = "0x63953eB1B3D8DB28334E7C1C69456C851F934199"
    actual = ethereum.decode_address(address)
    assert actual == expected


def test_encode_address(ethereum):
    raw_address = "0x63953eB1B3D8DB28334E7C1C69456C851F934199"
    address = AddressType(HexAddress(HexStr(raw_address)))
    actual = ethereum.encode_address(address)
    assert actual == raw_address


def test_transaction_dict_excludes_none_values():
    txn = StaticFeeTransaction()
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
        status=TransactionStatusEnum.FAILING,
        gas_price=0,
        block_number=0,
        sender="",
        receiver="",
        nonce=0,
    )
    with pytest.raises(OutOfGasError):
        receipt.raise_for_status()
