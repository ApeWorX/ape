from evm_trace import CallType
from evm_trace.display import DisplayableCallTreeNode
from hexbytes import HexBytes

CALL_TREE_DICT = {
    "call_type": CallType.CALL,
    "address": HexBytes("0x59Cbca9002F165730BD0CBCdd2559a79DDF8a054"),
    "value": 123,
    "depth": 0,
    "gas_limit": 492533,
    "gas_cost": 469604,
    "calldata": HexBytes("0x372dca07"),
    "returndata": HexBytes(
        "0x000000000000000000000000000000000000000000000000000000000000002000000000000000000000000000000000000000000000000000000000000000200000000000000000000000001e59ce931b4cfea3fe4b875411e280e173cb7a9c"  # noqa: E501
    ),
    "calls": [
        {
            "call_type": CallType.CALL,
            "address": HexBytes("0xbcf7fffd8b256ec51a36782a52d0c34f6474d951"),
            "value": 0,
            "depth": 1,
            "gas_limit": 468829,
            "gas_cost": 461506,
            "calldata": HexBytes(
                "0x045856de00000000000000000000000000000000000000000000000000000000000393cc"
            ),
            "returndata": HexBytes(
                "0x00000000000000000000000000000000000000000000000000001564ff3f0da300000000000000000000000000000000000000000000000000000002964619c700000000000000000000000000000000000000000000000000000000000393cc00000000000000000000000000000000000000000000000004cae9c39bdb4f7700000000000000000000000000000000000000000000000000005af310694bb20000000000000000000000000000000000000000011dc18b6f8f1601b7b1b33100000000000000000000000000000000000000000000000000000000000393cc000000000000000000000000000000000000000000000004ffd72d92184e6bb20000000000000000000000000000000000000000000000000000000000000d7e000000000000000000000000000000000000000000000006067396b875234f7700000000000000000000000000000000000000000000000000012f39bc807bb20000000000000000000000000000000000000002f5db749b3db467538fb1b331"
            ),
            "calls": [],
            "selfdestruct": False,
            "failed": False,
            "display_cls": DisplayableCallTreeNode,
        },
        {
            "call_type": CallType.CALL,
            "address": HexBytes("0xbcf7fffd8b256ec51a36782a52d0c34f6474d951"),
            "value": 0,
            "depth": 1,
            "gas_limit": 408447,
            "gas_cost": 402067,
            "calldata": HexBytes(
                "0xbeed0f8500000000000000000000000000000000000000000000000000000000000000400000000000000000000000000000000000000000011dc18b6f8f1601b7b1b33100000000000000000000000000000000000000000000000000000000000000096963652d637265616d0000000000000000000000000000000000000000000000"
            ),
            "returndata": HexBytes("0x"),
            "calls": [
                {
                    "call_type": CallType.STATICCALL,
                    "address": HexBytes("0x274b028b03a250ca03644e6c578d81f019ee1323"),
                    "value": 0,
                    "depth": 2,
                    "gas_limit": 375975,
                    "gas_cost": 370103,
                    "calldata": HexBytes("0x7007cbe8"),
                    "returndata": HexBytes(
                        "0x000000000000000000000000000000000293b0e3558d33b8a4c483e40e2b8db9000000000000000000000000000000000000000000000000018b932eebcc7eb90000000000000000000000000000000000bf550935e92f79f09e3530df8660c5"
                    ),
                    "calls": [],
                    "selfdestruct": False,
                    "failed": False,
                    "display_cls": DisplayableCallTreeNode,
                },
                {
                    "call_type": CallType.CALL,
                    "address": HexBytes("0x274b028b03a250ca03644e6c578d81f019ee1323"),
                    "value": 0,
                    "depth": 2,
                    "gas_limit": 369643,
                    "gas_cost": 363869,
                    "calldata": HexBytes(
                        "0x878fb70100000000000000000000000000000000000000000000000000000000000000600000000000000000000000000000000000000000011dc18b6f8f1601b7b1b331000000000000000000000000f2df0b975c0c9efa2f8ca0491c2d1685104d2488000000000000000000000000000000000000000000000000000000000000000773696d706c657200000000000000000000000000000000000000000000000000"
                    ),
                    "returndata": HexBytes("0x"),
                    "calls": [],
                    "selfdestruct": False,
                    "failed": False,
                    "display_cls": DisplayableCallTreeNode,
                },
            ],
            "selfdestruct": False,
            "failed": False,
            "display_cls": DisplayableCallTreeNode,
        },
        {
            "call_type": CallType.CALL,
            "address": HexBytes("0xbcf7fffd8b256ec51a36782a52d0c34f6474d951"),
            "value": 0,
            "depth": 1,
            "gas_limit": 237135,
            "gas_cost": 233432,
            "calldata": HexBytes(
                "0xb27b88040000000000000000000000001e59ce931b4cfea3fe4b875411e280e173cb7a9c"
            ),
            "returndata": HexBytes(
                "0x0000000000000000000000001e59ce931b4cfea3fe4b875411e280e173cb7a9c"
            ),
            "calls": [],
            "selfdestruct": False,
            "failed": False,
            "display_cls": DisplayableCallTreeNode,
        },
        {
            "call_type": CallType.CALL,
            "address": HexBytes("0xbcf7fffd8b256ec51a36782a52d0c34f6474d951"),
            "value": 0,
            "depth": 1,
            "gas_limit": 235631,
            "gas_cost": 231951,
            "calldata": HexBytes(
                "0xb9e5b20a0000000000000000000000001e59ce931b4cfea3fe4b875411e280e173cb7a9c"
            ),
            "returndata": HexBytes("0x"),
            "calls": [
                {
                    "call_type": CallType.STATICCALL,
                    "address": HexBytes("0x274b028b03a250ca03644e6c578d81f019ee1323"),
                    "value": 0,
                    "depth": 2,
                    "gas_limit": 230967,
                    "gas_cost": 227360,
                    "calldata": HexBytes(
                        "0xe5e1d93f000000000000000000000000f2df0b975c0c9efa2f8ca0491c2d1685104d2488"
                    ),
                    "returndata": HexBytes(
                        "0x00000000000000000000000000000000000000000000000000000000000000600000000000000000000000000000000000000000011dc18b6f8f1601b7b1b331000000000000000000000000f2df0b975c0c9efa2f8ca0491c2d1685104d2488000000000000000000000000000000000000000000000000000000000000000773696d706c657200000000000000000000000000000000000000000000000000"
                    ),
                    "calls": [],
                    "selfdestruct": False,
                    "failed": False,
                    "display_cls": DisplayableCallTreeNode,
                },
                {
                    "call_type": CallType.CALL,
                    "address": HexBytes("0x274b028b03a250ca03644e6c578d81f019ee1323"),
                    "value": 0,
                    "depth": 2,
                    "gas_limit": 225789,
                    "gas_cost": 222263,
                    "calldata": HexBytes(
                        "0x878fb70100000000000000000000000000000000000000000000000000000000000000600000000000000000000000000000000000000000000000000000000000000000000000000000000000000000274b028b03a250ca03644e6c578d81f019ee1323000000000000000000000000000000000000000000000000000000000000000773696d706c657200000000000000000000000000000000000000000000000000"
                    ),
                    "returndata": HexBytes("0x"),
                    "calls": [],
                    "selfdestruct": False,
                    "failed": False,
                    "display_cls": DisplayableCallTreeNode,
                },
                {
                    "call_type": CallType.CALL,
                    "address": HexBytes("0x274b028b03a250ca03644e6c578d81f019ee1323"),
                    "value": 0,
                    "depth": 2,
                    "gas_limit": 149571,
                    "gas_cost": 147236,
                    "calldata": HexBytes("0x90bb7141"),
                    "returndata": HexBytes("0x"),
                    "calls": [],
                    "selfdestruct": False,
                    "failed": False,
                    "display_cls": DisplayableCallTreeNode,
                },
                {
                    "call_type": CallType.CALL,
                    "address": HexBytes("0x274b028b03a250ca03644e6c578d81f019ee1323"),
                    "value": 0,
                    "depth": 2,
                    "gas_limit": 123951,
                    "gas_cost": 122016,
                    "calldata": HexBytes("0x90bb7141"),
                    "returndata": HexBytes("0x"),
                    "calls": [],
                    "selfdestruct": False,
                    "failed": False,
                    "display_cls": DisplayableCallTreeNode,
                },
            ],
            "selfdestruct": False,
            "failed": False,
            "display_cls": DisplayableCallTreeNode,
        },
        {
            "call_type": CallType.STATICCALL,
            "address": HexBytes("0x274b028b03a250ca03644e6c578d81f019ee1323"),
            "value": 0,
            "depth": 1,
            "gas_limit": 101895,
            "gas_cost": 100305,
            "calldata": HexBytes(
                "0xbff2e0950000000000000000000000001e59ce931b4cfea3fe4b875411e280e173cb7a9c"
            ),
            "returndata": HexBytes(
                "0x0000000000000000000000000000000000000000000000000000000000000000"
            ),
            "calls": [],
            "selfdestruct": False,
            "failed": False,
            "display_cls": DisplayableCallTreeNode,
        },
        {
            "call_type": CallType.STATICCALL,
            "address": HexBytes("0xbcf7fffd8b256ec51a36782a52d0c34f6474d951"),
            "value": 0,
            "depth": 1,
            "gas_limit": 95764,
            "gas_cost": 94270,
            "calldata": HexBytes(
                "0x9155fd570000000000000000000000001e59ce931b4cfea3fe4b875411e280e173cb7a9c"
            ),
            "returndata": HexBytes(
                "0x0000000000000000000000000000000000000000000000000000000000000000"
            ),
            "calls": [],
            "selfdestruct": False,
            "failed": False,
            "display_cls": DisplayableCallTreeNode,
        },
        {
            "call_type": CallType.CALL,
            "address": HexBytes("0xbcf7fffd8b256ec51a36782a52d0c34f6474d951"),
            "value": 0,
            "depth": 1,
            "gas_limit": 93784,
            "gas_cost": 92321,
            "calldata": HexBytes(
                "0xbeed0f850000000000000000000000000000000000000000000000000000000000000040000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000096c656d6f6e64726f700000000000000000000000000000000000000000000000"
            ),
            "returndata": HexBytes("0x"),
            "calls": [
                {
                    "call_type": CallType.STATICCALL,
                    "address": HexBytes("0x274b028b03a250ca03644e6c578d81f019ee1323"),
                    "value": 0,
                    "depth": 2,
                    "gas_limit": 87872,
                    "gas_cost": 86501,
                    "calldata": HexBytes("0x7007cbe8"),
                    "returndata": HexBytes(
                        "0x000000000000000000000000000000000293b0e3558d33b8a4c483e40e2b8db9000000000000000000000000000000000000000000000000018b932eebcc7eb90000000000000000000000000000000000bf550935e92f79f09e3530df8660c5"
                    ),
                    "calls": [],
                    "selfdestruct": False,
                    "failed": False,
                    "display_cls": DisplayableCallTreeNode,
                },
                {
                    "call_type": CallType.CALL,
                    "address": HexBytes("0x274b028b03a250ca03644e6c578d81f019ee1323"),
                    "value": 0,
                    "depth": 2,
                    "gas_limit": 84040,
                    "gas_cost": 82729,
                    "calldata": HexBytes(
                        "0x878fb70100000000000000000000000000000000000000000000000000000000000000600000000000000000000000000000000000000000000000000000000000000000000000000000000000000000f2df0b975c0c9efa2f8ca0491c2d1685104d2488000000000000000000000000000000000000000000000000000000000000000773696d706c657200000000000000000000000000000000000000000000000000"
                    ),
                    "returndata": HexBytes("0x"),
                    "calls": [],
                    "selfdestruct": False,
                    "failed": False,
                    "display_cls": DisplayableCallTreeNode,
                },
            ],
            "selfdestruct": False,
            "failed": False,
            "display_cls": DisplayableCallTreeNode,
        },
        {
            "call_type": CallType.CALL,
            "address": HexBytes("0xbcf7fffd8b256ec51a36782a52d0c34f6474d951"),
            "value": 0,
            "depth": 1,
            "gas_limit": 56127,
            "gas_cost": 55252,
            "calldata": HexBytes(
                "0xbeed0f850000000000000000000000000000000000000000000000000000000000000040000000000000000000000000000000000000000000000000000000000000006f0000000000000000000000000000000000000000000000000000000000000014736e6974636865735f6765745f73746963686573000000000000000000000000"
            ),
            "returndata": HexBytes("0x"),
            "calls": [
                {
                    "call_type": CallType.STATICCALL,
                    "address": HexBytes("0x274b028b03a250ca03644e6c578d81f019ee1323"),
                    "value": 0,
                    "depth": 2,
                    "gas_limit": 52903,
                    "gas_cost": 52079,
                    "calldata": HexBytes("0x7007cbe8"),
                    "returndata": HexBytes(
                        "0x000000000000000000000000000000000293b0e3558d33b8a4c483e40e2b8db9000000000000000000000000000000000000000000000000018b932eebcc7eb90000000000000000000000000000000000bf550935e92f79f09e3530df8660c5"
                    ),
                    "calls": [],
                    "selfdestruct": False,
                    "failed": False,
                    "display_cls": DisplayableCallTreeNode,
                },
                {
                    "call_type": CallType.CALL,
                    "address": HexBytes("0x274b028b03a250ca03644e6c578d81f019ee1323"),
                    "value": 0,
                    "depth": 2,
                    "gas_limit": 49071,
                    "gas_cost": 48306,
                    "calldata": HexBytes(
                        "0x878fb7010000000000000000000000000000000000000000000000000000000000000060000000000000000000000000000000000000000000000000000000000000006f000000000000000000000000f2df0b975c0c9efa2f8ca0491c2d1685104d2488000000000000000000000000000000000000000000000000000000000000000773696d706c657200000000000000000000000000000000000000000000000000"
                    ),
                    "returndata": HexBytes("0x"),
                    "calls": [],
                    "selfdestruct": False,
                    "failed": False,
                    "display_cls": DisplayableCallTreeNode,
                },
            ],
            "selfdestruct": False,
            "failed": False,
            "display_cls": DisplayableCallTreeNode,
        },
    ],
    "selfdestruct": False,
    "failed": False,
    "display_cls": DisplayableCallTreeNode,
}
