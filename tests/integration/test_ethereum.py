import pytest

from ape.api import TransactionType


@pytest.mark.parametrize("type_kwarg", (0, "0x0", b"0x0", "0"))
def test_create_static_fee_transaction(ethereum, type_kwarg):
    txn = ethereum.create_transaction(type=type_kwarg)
    assert txn.type == TransactionType.STATIC.value


@pytest.mark.parametrize("type_kwarg", (None, 2, "0x2", b"0x2", "2"))
def test_create_dynamic_fee_transaction(ethereum, type_kwarg):
    txn = ethereum.create_transaction(type=type_kwarg)
    assert txn.type == TransactionType.DYNAMIC.value
