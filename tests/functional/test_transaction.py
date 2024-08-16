import re
import warnings
from typing import Optional

import pytest
from eth_pydantic_types import HexBytes
from eth_utils import to_hex
from hexbytes import HexBytes as BaseHexBytes

from ape.api import TransactionAPI
from ape.exceptions import SignatureError
from ape_ethereum.transactions import (
    AccessList,
    AccessListTransaction,
    DynamicFeeTransaction,
    StaticFeeTransaction,
    TransactionType,
)

ACCESS_LIST = [{"address": "0x0000000000000000000000000000000000000004", "storageKeys": []}]

ACCESS_LIST_HEXBYTES = [
    {
        "address": "0x0000000000000000000000000000000000000004",
        "storageKeys": [
            BaseHexBytes("0x0000000000000000000000000000000000000000000000000000000000000000")
        ],
    }
]

# NOTE: Long access List also uses / tests HexBytes from eth_pydantic_types\
#   (which shouldn't matter).
LONG_ACCESS_LIST = [
    {
        "address": "0x5Ab952D45d33ba32DBAA3Da85b0738aC9DF24626",
        "storageKeys": [
            HexBytes("0x0000000000000000000000000000000000000000000000000000000000000000"),
            HexBytes("0x0000000000000000000000000000000000000000000000000000000000000004"),
            HexBytes("0x0000000000000000000000000000000000000000000000000000000000000001"),
            HexBytes("0x9c04773acff4c5c42718bd0120c72761f458e43068a3961eb935577d1ed4effb"),
            HexBytes("0x0000000000000000000000000000000000000000000000000000000000000008"),
        ],
    },
    {
        "address": "0x60594a405d53811d3BC4766596EFD80fd545A270",
        "storageKeys": [
            HexBytes("0x2e7eb34672b18adb9244b4932b747ae4bcb4f839a51cd3b2e72e6113c9d4d285"),
            HexBytes("0x000000000000000000000000000000000000000000000000000000000000005c"),
            HexBytes("0x000000000000000000000000000000000000000000000000000000000000005d"),
            HexBytes("0x0000000000000000000000000000000000000000000000000000000000000000"),
            HexBytes("0x0000000000000000000000000000000000000000000000000000000000000004"),
            HexBytes("0x0000000000000000000000000000000000000000000000000000000000000002"),
        ],
    },
    {
        "address": "0x6B175474E89094C44Da98b954EedeAC495271d0F",
        "storageKeys": [
            HexBytes("0x29cb8bd4e192d16f51155329ce8b0f5eb88a1d9e4d3b93ce07efbac9e1c4d175"),
            HexBytes("0x995f3b129dd3291868ddb9cf202c75cd985227d50e309847fbab0f8da403b19c"),
        ],
    },
    {
        "address": "0x709b80deC74CA88e9394DEaB45840d861BD5398d",
        "storageKeys": [
            HexBytes("0x0000000000000000000000000000000000000000000000000000000000000006"),
            HexBytes("0x0000000000000000000000000000000000000000000000000000000000000007"),
            HexBytes("0x0000000000000000000000000000000000000000000000000000000000000009"),
            HexBytes("0x000000000000000000000000000000000000000000000000000000000000000a"),
            HexBytes("0x000000000000000000000000000000000000000000000000000000000000000c"),
            HexBytes("0x0000000000000000000000000000000000000000000000000000000000000008"),
        ],
    },
    {
        "address": "0x45E412E1878080815D6D51d47B83D17869433459",
        "storageKeys": [
            HexBytes("0x0000000000000000000000000000000000000000000000000000000000000005"),
            HexBytes("0x0000000000000000000000000000000000000000000000000000000000000008"),
            HexBytes("0x3a8870f40d200d252a256529d1f22c4f977b6e09dc78c6ebdeffd3f8651c4719"),
            HexBytes("0x2d027208e382c51007968756a0988c06fc25a78a1ef13c193023db7354fa6ea9"),
            HexBytes("0xc247e5713292da7b6b8145ca699e5c90c1257a929a9b107aa7c7d211bc3a369c"),
            HexBytes("0x50164d12bd200c7817ac53416fd234974ec726930dca7760174d351e0e29af6a"),
            HexBytes("0x000000000000000000000000000000000000000000000000000000000000000f"),
            HexBytes("0xb8e6a40a2729c4eca72da15a47bea21de47ee5b868eb98a2a3966fe05bc777c6"),
            HexBytes("0x1e4e2ca44a4ccf068a5ab14ea9a4d61e97a8b5395bf782d9b2032e0ee8487c29"),
            HexBytes("0x000000000000000000000000000000000000000000000000000000000000000b"),
            HexBytes("0x5de84563fdc81a8663ce72466e3e1e667da5e6c8834c90c011812476ee214f3c"),
            HexBytes("0xb39e9ba92c3c47c76d4f70e3bc9c3270ab78d2592718d377c8f5433a34d3470a"),
            HexBytes("0x86853267f2534b9eec92fd7a80680d7481e5e740ce8d21c54361341b3a3c1f14"),
            HexBytes("0xa78b521343fce79b129d9bbe9bff921a08c8a8fde6ae24a7e159847b3ba54bb7"),
            HexBytes("0x0000000000000000000000000000000000000000000000000000000000000010"),
            HexBytes("0x000000000000000000000000000000000000000000000000000000000000000a"),
            HexBytes("0x000000000000000000000000000000000000000000000000000000000000001d"),
            HexBytes("0x0000000000000000000000000000000000000000000000000000000000000009"),
            HexBytes("0x21c632ec26149a6f0282e6b24bf8cb49cdf334cfb6e21a8f4001c5e39c858863"),
        ],
    },
    {
        "address": "0xFb76CD5e9Fb9351137C3CE0aC1C23212C46995A7",
        "storageKeys": [
            HexBytes("0x0000000000000000000000000000000000000000000000000000000000000002"),
            HexBytes("0x9c04773acff4c5c42718bd0120c72761f458e43068a3961eb935577d1ed4effb"),
            HexBytes("0x0000000000000000000000000000000000000000000000000000000000000008"),
            HexBytes("0x0000000000000000000000000000000000000000000000000000000000000000"),
            HexBytes("0x0000000000000000000000000000000000000000000000000000000000000004"),
        ],
    },
    {
        "address": "0x3005003BDA885deE7c74182e5FE336e9E3Df87bB",
        "storageKeys": [
            HexBytes("0x23d376ed44ad443baf938cf24280e50027474804f2cdc01ec9195cdc123467a5"),
            HexBytes("0x577b913a3c8810dd10161c9ae11e2ee31042564c62114c83b0bc5d3a3e71b362"),
            HexBytes("0x04421adc6f4dd2e52160b542e3ea06d21bd261fae596660765cf3964443fa2b7"),
        ],
    },
    {
        "address": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
        "storageKeys": [
            HexBytes("0xbb0d37a1af2c606132ece9f63118a24cfb959e4791cb65d639217bd82f7282b3"),
            HexBytes("0xf762dfe765e313d39f5dd6e34e29a9ef0af51578e67f7f482bb4f8efd984976b"),
            HexBytes("0xa3303497cfb83efa67ca4f88b647c0dc6639b10da44cd96ac8b3488d155cf935"),
            HexBytes("0xb73247ebb5deb7b0fcdb78323c538aca3746ddf79808af84f3cf760fcb915185"),
            HexBytes("0x12231cd4c753cb5530a43a74c45106c24765e6f81dc8927d4f4be7e53315d5a8"),
        ],
    },
]


@pytest.fixture
def access_list():
    return ACCESS_LIST


@pytest.mark.parametrize("type_kwarg", (0, "0x0", b"\x00", "0", HexBytes("0x0"), HexBytes("0x00")))
def test_type_0_transactions(ethereum, type_kwarg):
    txn = ethereum.create_transaction(type=type_kwarg)
    assert txn.type == TransactionType.STATIC.value


@pytest.mark.parametrize("type_kwarg", (1, "0x01", b"\x01", "1", "01", HexBytes("0x01")))
def test_type_1_transactions(ethereum, type_kwarg):
    txn = ethereum.create_transaction(type=type_kwarg)
    assert txn.type == TransactionType.ACCESS_LIST.value


@pytest.mark.parametrize("type_kwarg", (None, 2, "0x02", b"\x02", "2", "02", HexBytes("0x02")))
def test_type_2_transactions(ethereum, type_kwarg):
    txn = ethereum.create_transaction(type=type_kwarg)
    assert txn.type == TransactionType.DYNAMIC.value


@pytest.mark.parametrize("key", ("accessList", "access_list"))
def test_type_1_transactions_using_access_list(ethereum, access_list, key):
    """
    If not given type and only given accessList, the assumed type is 1,
    an "access-list" transaction.
    """
    data = {key: access_list}
    txn = ethereum.create_transaction(**data)
    assert txn.type == 1


@pytest.mark.parametrize("key", ("accessList", "access_list"))
def test_type_2_transactions_with_max_fee_and_access_list(ethereum, access_list, key):
    """
    Dynamic-fee txns also support access lists, so the presence of max_fee
    with access_list implies a type 2 txn.
    """
    data = {"max_fee": 1000000000, key: access_list}
    txn = ethereum.create_transaction(**data)
    assert txn.type == 2
    assert txn.max_fee == 1000000000


def test_type_2_transactions_with_access_list(ethereum, access_list):
    txn = ethereum.create_transaction(type=2, accessList=access_list)
    assert txn.type == TransactionType.DYNAMIC.value
    assert txn.access_list == [AccessList.model_validate(x) for x in access_list]


@pytest.mark.parametrize(
    "tx_kwargs",
    [{"type": 3}, {"max_fee_per_blob_gas": 123}, {"blob_versioned_hashes": [HexBytes(123)]}],
)
def test_type_3_transactions(ethereum, tx_kwargs):
    txn = ethereum.create_transaction(**tx_kwargs)
    assert txn.type == 3


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
def test_type_2_transactions_using_fee_kwargs(ethereum, fee_kwargs):
    txn = ethereum.create_transaction(**fee_kwargs)
    assert isinstance(txn, DynamicFeeTransaction)
    if "max_priority_fee" in fee_kwargs:
        assert txn.max_priority_fee == int(1e9)
    if "max_fee" in fee_kwargs:
        assert txn.max_fee == int(100e9)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"type": 0},
        {"type": 1},
        {"type": 1, "accessList": ACCESS_LIST},
        {"type": 1, "accessList": LONG_ACCESS_LIST},
        {"type": 2, "max_fee": 1_000_000_000},
        {"type": 2, "accessList": ACCESS_LIST},
        {"type": 2, "accessList": ACCESS_LIST_HEXBYTES},
    ],
)
def test_txn_hash_and_receipt(owner, eth_tester_provider, ethereum, kwargs):
    txn = ethereum.create_transaction(**kwargs)
    txn = owner.prepare_transaction(txn)
    txn = owner.sign_transaction(txn)
    assert txn
    actual = to_hex(txn.txn_hash)
    receipt = eth_tester_provider.send_transaction(txn)

    # Show that we can access the receipt from the transaction.
    assert txn.receipt == receipt

    expected = receipt.txn_hash

    assert actual == expected


def test_txn_hash_when_access_list_is_raw(ethereum, owner):
    """
    Tests against a condition I was never able to reproduce where
    a transaction's access list contained bytes-values and that
    causes the serialization to error.
    """

    txn = ethereum.create_transaction(accessList=ACCESS_LIST_HEXBYTES, type=2)
    txn = owner.prepare_transaction(txn)
    txn = owner.sign_transaction(txn)

    # Hack to make access_list raw. I am not sure how a user would get
    # to this state, but somehow they have.
    txn.access_list = ACCESS_LIST_HEXBYTES

    # Ignore the Pydantic warning from access-list being the wrong type.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        actual = to_hex(txn.txn_hash)

    assert actual.startswith("0x")


def test_data_when_contains_whitespace():
    data = b"Should not clip whitespace\t\n"
    txn_dict = {"data": data}
    txn = StaticFeeTransaction.model_validate(txn_dict)
    assert txn.data == data, "Whitespace should not be removed from data"


def test_model_dump_excludes_none_values():
    txn = StaticFeeTransaction(sender=None)
    txn.value = 1000000
    actual = txn.model_dump()
    assert "value" in actual
    txn.value = None  # type: ignore
    actual = txn.model_dump()
    assert "value" not in actual


def test_model_dump_access_list():
    # Data directly from eth_createAccessList RPC
    access_list = [
        {
            "address": "0x7ef8e99980da5bcedcf7c10f41e55f759f6a174b",
            "storageKeys": [
                "0x0000000000000000000000000000000000000000000000000000000000000000",
                "0x0000000000000000000000000000000000000000000000000000000000000001",
                "0x0000000000000000000000000000000000000000000000000000000000000002",
            ],
        }
    ]
    txn = AccessListTransaction(access_list=access_list, sender=None)
    actual = txn.model_dump(exclude_none=True, by_alias=True)
    assert actual is not None


def test_str_when_data_is_bytes(ethereum):
    """
    Tests against a condition that would cause transactions to
    fail with string-encoding errors.
    """
    txn = ethereum.create_transaction(data=HexBytes("0x123"))
    actual = str(txn)
    assert isinstance(actual, str)


def test_receipt_when_none(ethereum):
    txn = ethereum.create_transaction(data=HexBytes("0x123"))
    assert txn.receipt is None


def test_repr(ethereum):
    txn = ethereum.create_transaction(data=HexBytes("0x123"))
    actual = repr(txn)
    expected = (
        r"<DynamicFeeTransaction chainId=\d*, "
        r"gas=\d*, value=0, data=0x\d*, type=2, accessList=\[\]>"
    )
    assert re.match(expected, actual)


# NOTE: Some of these values are needed for signing to work.
@pytest.mark.parametrize(
    "tx_kwargs",
    [
        {"data": HexBytes("0x123"), "nonce": 0, "gas_price": 0},
        {"gasLimit": 100, "nonce": 0, "max_fee": 0, "max_priority_fee": 0},
        {"access_list": ACCESS_LIST, "nonce": 0, "gasPrice": 0},  # NOTE: show camelCase works
        {
            "accessList": ACCESS_LIST_HEXBYTES,
            "nonce": 0,
            "max_fee": 0,
            "max_priority_fee": 0,
            "type": 2,
        },
        {
            "access_list": LONG_ACCESS_LIST,
            "nonce": 0,
            "max_fee": 0,
            "max_priority_fee": 0,
            "type": 2,
        },
    ],
)
def test_serialize_transaction(owner, ethereum, tx_kwargs):
    txn = ethereum.create_transaction(**tx_kwargs)
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


class TestAccessList:
    @pytest.mark.parametrize(
        "address",
        (
            "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
            HexBytes("0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"),
        ),
    )
    def test_address(self, address):
        actual = AccessList(address=address, storageKeys=[])
        assert actual.address == "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"

    @pytest.mark.parametrize("storage_key", (123, HexBytes(123), "0x0123"))
    def test_storage_keys(self, storage_key, zero_address):
        actual = AccessList(address=zero_address, storageKeys=[storage_key])
        assert actual.storage_keys == [HexBytes(storage_key)]


def test_override_annotated_fields():
    """
    This test is to prove that a user may use an `int` for a base-class
    when the API field is described as a `HexInt`.
    """

    class MyTransaction(TransactionAPI):
        @property
        def txn_hash(self) -> HexBytes:
            return HexBytes("")

        def serialize_transaction(self) -> bytes:
            return b""

        chain_id: Optional[int] = None  # The base type is `Optional[HexInt]`.

    chain_id = 123123123123123123123123123123
    tx_type = 120
    my_tx = MyTransaction.model_validate({"chain_id": chain_id, "type": tx_type})
    assert my_tx.chain_id == chain_id
    assert my_tx.type == tx_type
