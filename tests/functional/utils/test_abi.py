import pickle
from copy import deepcopy

import pytest
from eth_pydantic_types import HexBytes
from ethpm_types.abi import ABIType, EventABI, EventABIType

from ape.utils.abi import LogInputABICollection, create_struct


@pytest.fixture
def event_abi():
    return EventABI(
        type="event",
        name="NodeOperatorAdded",
        inputs=[
            EventABIType(
                name="nodeOperatorId",
                type="uint256",
                components=None,
                internalType=None,
                indexed=False,
            ),
            EventABIType(
                name="name", type="string", components=None, internalType=None, indexed=False
            ),
            EventABIType(
                name="rewardAddress",
                type="address",
                components=None,
                internalType=None,
                indexed=False,
            ),
            EventABIType(
                name="stakingLimit",
                type="uint64",
                components=None,
                internalType=None,
                indexed=False,
            ),
        ],
        anonymous=False,
    )


@pytest.fixture
def collection(event_abi):
    return LogInputABICollection(event_abi)


@pytest.fixture
def topics():
    return ["0xc52ec0ad7872dae440d886040390c13677df7bf3cca136d8d81e5e5e7dd62ff1"]


@pytest.fixture(scope="module")
def log_data_missing_trailing_zeroes():
    return HexBytes(
        "0x000000000000000000000000000000000000000000000000000000000000001e"
        "000000000000000000000000000000000000000000000000000000000000008000"
        "00000000000000000000005a8b929edbf3ce44526465dd2087ec7efb59a5610000"
        "000000000000000000000000000000000000000000000000000000000000000000"
        "000000000000000000000000000000000000000000000000000000000b4c61756e"
        "63686e6f646573"
    )


def test_decode_data_missing_trailing_zeroes(
    collection, topics, log_data_missing_trailing_zeroes, ape_caplog
):
    """
    This test is for a time where Alchemy gave us log data when it was missing trailing zeroes.
    When using strict=False, it was able to properly decode. In this case, in Ape, we warn
    the user and still proceed to decode the log.
    """
    actual = ape_caplog.assert_last_log_with_retries(
        lambda: collection.decode(topics, log_data_missing_trailing_zeroes),
        "However, we are able to get a value using decode(strict=False)",
    )
    expected = {
        "name": "Launchnodes",
        "nodeOperatorId": 30,
        "rewardAddress": "0x5a8b929edbf3ce44526465dd2087ec7efb59a561",
        "stakingLimit": 0,
    }
    assert actual == expected


def test_decode_topics_missing_leading_zeroes(vyper_contract_type):
    # The second value here was the problem before... It has no leading zeroes
    # and eth-abi is very strict about that.
    topics = [
        "0xa84473122c11e32cd505595f246a28418b8ecd6cf819f4e3915363fad1b8f968",
        "0x0141",
        "0x9f3d45ac20ccf04b45028b8080bb191eab93e29f7898ed43acf480dd80bba94d",
    ]

    # NOTE: data isn't really part of the test but still has to be included.
    data = (
        b"\x9c\xe2\xce\xf5\x9b\xf2\xdeu\x83f\xf8s\xdb\x7f&\xef\xab\x9bw\xf7\xcf"
        b"\xe9\xc8I\xb6\xb5@\x04g\xa9)\x86\x00\x00\x00\x00\x00\x00\x00\x00\x00"
        b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
        b"\x00\x00\x00\x00\x00{\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
        b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
        b"\x00\x00`\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
        b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x07"
        b"Dynamic\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
        b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    )
    abi = vyper_contract_type.events["NumberChange"]
    collection = LogInputABICollection(abi)

    actual = collection.decode(topics, data)
    assert actual["newNum"] == 321  # NOTE: Was a bug where this causes issues.


class TestStruct:
    @pytest.fixture
    def struct(self):
        return create_struct(
            "MyStruct", (ABIType(name="proptest", type="string"),), ("output_value_0",)
        )

    def test_get_and_set_item(self, struct):
        assert struct["proptest"] == "output_value_0"
        struct["proptest"] = "something else"
        assert struct["proptest"] == "something else"

    def test_is_equal(self, struct):
        # Show struct equality works when props are the same.
        assert struct == struct  # even self
        new_struct = deepcopy(struct)
        assert struct == new_struct
        # Show changing a property makes them unequal.
        new_struct["proptest"] = "something else"
        assert struct != new_struct
        # Show testing with other types works w/o erroring.
        assert struct != 47

    def test_contains(self, struct):
        assert "proptest" in struct

    def test_len(self, struct):
        assert len(struct) == 1

    def test_items(self, struct):
        actual = struct.items()
        assert len(actual) == 1
        assert actual[0] == ("proptest", "output_value_0")

    def test_values(self, struct):
        actual = struct.values()
        assert len(actual) == 1
        assert actual[0] == "output_value_0"

    def test_pickle(self, struct):
        actual = pickle.dumps(struct)
        assert isinstance(actual, bytes)

    def test_field_with_same_name_as_method(self):
        struct = create_struct(
            "MyStruct", (ABIType(name="values", type="string"),), ("output_value_0",)
        )
        assert struct.values == "output_value_0"  # Is the field, not the method.
