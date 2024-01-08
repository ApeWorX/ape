import pytest
from eth_pydantic_types import HexBytes

from ape.exceptions import SignatureError
from ape_ethereum.transactions import DynamicFeeTransaction, StaticFeeTransaction, TransactionType


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


@pytest.mark.parametrize(
    "fee_kwargs",
    (
        {"max_fee": "100 gwei"},
        {"max_fee": int(100e9)},
        {"max_priority_fee": "1 gwei"},
        {"max_priority_fee": int(1e9)},
        {"max_priority_fee": "1 gwei", "max_fee": "100 gwei"},
        {"max_priority_fee": int(1e9), "max_fee": "100 gwei"},
        {"max_priority_fee": "1 gwei", "max_fee": int(100e9)},
        {"max_priority_fee": int(1e9), "max_fee": int(100e9)},
    ),
)
def test_create_dynamic_fee_kwargs(ethereum, fee_kwargs):
    txn = ethereum.create_transaction(**fee_kwargs)
    assert isinstance(txn, DynamicFeeTransaction)
    if "max_priority_fee" in fee_kwargs:
        assert txn.max_priority_fee == int(1e9)
    if "max_fee" in fee_kwargs:
        assert txn.max_fee == int(100e9)


def test_txn_hash_and_receipt(owner, eth_tester_provider, ethereum):
    txn = ethereum.create_transaction()
    txn = owner.prepare_transaction(txn)
    txn = owner.sign_transaction(txn)
    assert txn

    actual = txn.txn_hash.hex()
    receipt = eth_tester_provider.send_transaction(txn)

    # Show that we can access the receipt from the transaction.
    assert txn.receipt == receipt

    expected = receipt.txn_hash

    assert actual == expected


def test_whitespace_in_transaction_data():
    data = b"Should not clip whitespace\t\n"
    txn_dict = {"data": data}
    txn = StaticFeeTransaction.model_validate(txn_dict)
    assert txn.data == data, "Whitespace should not be removed from data"


def test_transaction_dict_excludes_none_values():
    txn = StaticFeeTransaction()
    txn.value = 1000000
    actual = txn.model_dump(mode="json")
    assert "value" in actual
    txn.value = None  # type: ignore
    actual = txn.model_dump(mode="json")
    assert "value" not in actual


def test_txn_str_when_data_is_bytes(ethereum):
    """
    Tests against a condition that would cause transactions to
    fail with string-encoding errors.
    """
    txn = ethereum.create_transaction(data=HexBytes("0x123"))
    actual = str(txn)
    assert isinstance(actual, str)


def test_transaction_with_none_receipt(ethereum):
    txn = ethereum.create_transaction(data=HexBytes("0x123"))
    assert txn.receipt is None


def test_serialize_transaction(owner, ethereum):
    txn = ethereum.create_transaction(
        data=HexBytes("0x123"), max_fee=0, max_priority_fee=0, nonce=0
    )
    txn = owner.sign_transaction(txn)
    assert txn is not None

    actual = txn.serialize_transaction()
    assert isinstance(actual, bytes)


def test_serialize_transaction_missing_signature(ethereum, owner):
    expected = r"The transaction is not signed."
    txn = ethereum.create_transaction(data=HexBytes("0x123"), sender=owner.address)
    with pytest.raises(SignatureError, match=expected):
        txn.serialize_transaction()


def test_serialize_transaction_missing_signature_and_sender(ethereum):
    expected = (
        r"The transaction is not signed. "
        r"Did you forget to add the `sender=` kwarg to the transaction function call?"
    )
    txn = ethereum.create_transaction(data=HexBytes("0x123"))
    with pytest.raises(SignatureError, match=expected):
        txn.serialize_transaction()
