import pickle
from copy import deepcopy

import pytest
from eth_pydantic_types import HexBytes
from ethpm_types.abi import ABIType, EventABI, EventABIType, MethodABI

from ape.exceptions import MissingStructFieldError
from ape.utils.abi import LogInputABICollection, StructParser, create_struct


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


def test_decode_topics_missing_leading_zeroes(project):
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
    abi = project.VyperContract.contract_type.events["NumberChange"]
    collection = LogInputABICollection(abi)

    actual = collection.decode(topics, data)
    assert actual["newNum"] == 321  # NOTE: Was a bug where this causes issues.


_ID_COMPONENT = {"name": "id", "type": "uint256", "internalType": "uint256"}
_POINT_COMPONENTS = [
    {"name": "x", "type": "uint256", "internalType": "uint256"},
    {"name": "y", "type": "uint256", "internalType": "uint256"},
]
# struct Point { uint256 x; uint256 y; }
_POINT = {
    "name": "point",
    "type": "tuple",
    "internalType": "struct Nested.Point",
    "components": _POINT_COMPONENTS,
}
_POINT_ARRAY = {
    **_POINT,
    "name": "cells",
    "type": "tuple[3]",
    "internalType": "struct Nested.Point[3]",
}
_DYNAMIC_POINT_ARRAY = {
    **_POINT_ARRAY,
    "type": "tuple[]",
    "internalType": "struct Nested.Point[]",
}
# struct Row { uint256 id; Point[3] cells; }
_ROW = {
    "name": "row",
    "type": "tuple",
    "internalType": "struct Nested.Row",
    "components": [_ID_COMPONENT, _POINT_ARRAY],
}
_ROW_ARRAY = {**_ROW, "type": "tuple[2]", "internalType": "struct Nested.Row[2]"}
# struct DynRow { uint256 id; Point[] cells; }
_DYN_ROW = {
    **_ROW,
    "internalType": "struct Nested.DynRow",
    "components": [_ID_COMPONENT, _DYNAMIC_POINT_ARRAY],
}
# struct Deep { uint256 id; DynRow[2] rows; }
_DEEP = {
    "name": "deep",
    "type": "tuple",
    "internalType": "struct Nested.Deep",
    "components": [
        _ID_COMPONENT,
        {**_DYN_ROW, "name": "rows", "type": "tuple[2]"},
    ],
}
# struct Wrapper { uint256 id; Point point; }
_WRAPPER = {
    "name": "wrapper",
    "type": "tuple",
    "internalType": "struct Nested.Wrapper",
    "components": [_ID_COMPONENT, _POINT],
}
# struct NumRow { uint256 id; uint256[3] nums; }
_NUM_ROW = {
    "name": "numRow",
    "type": "tuple",
    "internalType": "struct Nested.NumRow",
    "components": [
        _ID_COMPONENT,
        {"name": "nums", "type": "uint256[3]", "internalType": "uint256[3]"},
    ],
}
_POINT_DICTS = [{"x": 1, "y": 2}, {"x": 3, "y": 4}, {"x": 5, "y": 6}]
_ENCODED_ROW = (1, [(1, 2), (3, 4), (5, 6)])


def _point_struct(x, y):
    types = [ABIType.model_validate(c) for c in _POINT_COMPONENTS]
    return create_struct("Point", types, (x, y))


def _row_struct(id_, cells):
    types = [ABIType.model_validate(c) for c in (_ID_COMPONENT, _POINT_ARRAY)]
    return create_struct("Row", types, (id_, cells))


def _encode_input(input_type, value):
    abi = MethodABI.model_validate(
        {
            "type": "function",
            "name": "useStruct",
            "stateMutability": "nonpayable",
            "inputs": [input_type],
            "outputs": [],
        }
    )
    return StructParser(abi).encode_input([value])


class TestStructParserEncodeInput:
    @pytest.mark.parametrize(
        "input_type,value,expected",
        [
            # A struct field that is an array of structs, fixed and dynamic sized.
            (_ROW, {"id": 1, "cells": _POINT_DICTS}, _ENCODED_ROW),
            (_DYN_ROW, {"id": 1, "cells": _POINT_DICTS}, _ENCODED_ROW),
            (_ROW, {"id": 1, "cells": tuple(_POINT_DICTS)}, _ENCODED_ROW),
            # An array of structs that each have a struct-array field.
            (
                _ROW_ARRAY,
                [{"id": 1, "cells": _POINT_DICTS}, {"id": 1, "cells": _POINT_DICTS}],
                [_ENCODED_ROW, _ENCODED_ROW],
            ),
            # A struct-array field whose structs have a struct-array field themselves.
            (
                _DEEP,
                {
                    "id": 1,
                    "rows": [
                        {"id": 2, "cells": [{"x": 3, "y": 4}]},
                        {"id": 5, "cells": [{"x": 6, "y": 7}]},
                    ],
                },
                (1, [(2, [(3, 4)]), (5, [(6, 7)])]),
            ),
            # The same fields given as structs instead of dicts.
            (_ROW, {"id": 1, "cells": [_point_struct(1, 2), *_POINT_DICTS[1:]]}, _ENCODED_ROW),
            (
                _ROW,
                _row_struct(1, [_point_struct(x, y) for x, y in ((1, 2), (3, 4), (5, 6))]),
                _ENCODED_ROW,
            ),
            (_WRAPPER, {"id": 1, "point": _point_struct(2, 3)}, (1, (2, 3))),
        ],
    )
    def test_struct_field_of_structs(self, input_type, value, expected):
        actual = _encode_input(input_type, value)
        assert actual == [expected]
        # NOTE: A struct is equal to the tuple it represents, so ``==`` alone
        #   would not notice a field that was left as a struct or a dict.
        assert repr(actual) == repr([expected])

    @pytest.mark.parametrize(
        "input_type,value,expected",
        [
            # A plain array field is not a struct array.
            (_NUM_ROW, {"id": 1, "nums": [2, 3, 4]}, (1, [2, 3, 4])),
            # A single nested struct given as a dict.
            (_WRAPPER, {"id": 1, "point": {"x": 2, "y": 3}}, (1, (2, 3))),
            # An empty dynamic struct-array field.
            (_DYN_ROW, {"id": 1, "cells": []}, (1, [])),
            # A struct array given directly as an argument.
            (_POINT_ARRAY, _POINT_DICTS, [(1, 2), (3, 4), (5, 6)]),
            # A struct given positionally keeps its members in order, as-is.
            (_ROW, [1, [[1, 2], [3, 4], [5, 6]]], (1, [[1, 2], [3, 4], [5, 6]])),
        ],
    )
    def test_unaffected_shapes(self, input_type, value, expected):
        actual = _encode_input(input_type, value)
        assert actual == [expected]

    def test_struct_field_of_positional_structs(self):
        # Elements given positionally come back as tuples, which eth-abi accepts
        # the same as the lists it was given before.
        actual = _encode_input(_ROW, {"id": 1, "cells": [[1, 2], [3, 4], [5, 6]]})
        assert actual == [_ENCODED_ROW]

    def test_missing_struct_field(self):
        with pytest.raises(MissingStructFieldError):
            _encode_input(_ROW, {"id": 1})


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
        assert struct == struct  # even self  # noqa: PLR0124
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
