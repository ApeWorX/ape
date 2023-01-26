import pytest
from hexbytes import HexBytes

from ape_ethereum.transactions import StaticFeeTransaction, TransactionType


@pytest.mark.parametrize("type_kwarg", (0, "0x0", b"\x00", "0", HexBytes("0x0"), HexBytes("0x00")))
def test_create_static_fee_transaction(ethereum, type_kwarg):
    txn = ethereum.create_transaction(type=type_kwarg)
    assert txn.type == TransactionType.STATIC.value


@pytest.mark.parametrize("type_kwarg", (1, "0x01", b"\x01", "1", "01", HexBytes("0x01")))
def test_create_access_list_transaction(ethereum, type_kwarg):
    txn = ethereum.create_transaction(type=type_kwarg)
    assert txn.type == TransactionType.ACCESS_LIST.value


@pytest.mark.parametrize("type_kwarg", (None, 2, "0x02", b"\x02", "2", "02", HexBytes("0x02")))
def test_create_dynamic_fee_transaction(ethereum, type_kwarg):
    txn = ethereum.create_transaction(type=type_kwarg)
    assert txn.type == TransactionType.DYNAMIC.value


def test_txn_hash(owner, eth_tester_provider, ethereum):
    txn = ethereum.create_transaction()
    txn = owner.prepare_transaction(txn)
    txn = owner.sign_transaction(txn)
    assert txn

    actual = txn.txn_hash.hex()
    receipt = eth_tester_provider.send_transaction(txn)
    expected = receipt.txn_hash

    assert actual == expected


def test_whitespace_in_transaction_data():
    data = b"Should not clip whitespace\t\n"
    txn_dict = {"data": data}
    txn = StaticFeeTransaction.parse_obj(txn_dict)
    assert txn.data == data, "Whitespace should not be removed from data"


def test_transaction_dict_excludes_none_values():
    txn = StaticFeeTransaction()
    txn.value = 1000000
    actual = txn.dict()
    assert "value" in actual
    txn.value = None  # type: ignore
    actual = txn.dict()
    assert "value" not in actual
