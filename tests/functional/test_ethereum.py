import pytest
from hexbytes import HexBytes

from ape.api import TransactionType


@pytest.mark.parametrize("type_kwarg", (0, "0x0", b"\x00", "0", HexBytes("0x0"), HexBytes("0x00")))
def test_create_static_fee_transaction(ethereum, type_kwarg):
    txn = ethereum.create_transaction(type=type_kwarg)
    assert txn.type == TransactionType.STATIC


@pytest.mark.parametrize("type_kwarg", (None, 2, "0x02", b"\x02", "2", "02", HexBytes("0x02")))
def test_create_dynamic_fee_transaction(ethereum, type_kwarg):
    txn = ethereum.create_transaction(type=type_kwarg)
    assert txn.type == TransactionType.DYNAMIC.value
