import pytest
from eth_pydantic_types import HexBytes
from ethpm_types.abi import EventABI, EventABIType

from ape.utils.abi import LogInputABICollection


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


@pytest.fixture
def log_data_missing_trailing_zeroes():
    return HexBytes(
        "0x000000000000000000000000000000000000000000000000000000000000001e"
        "000000000000000000000000000000000000000000000000000000000000008000"
        "00000000000000000000005a8b929edbf3ce44526465dd2087ec7efb59a5610000"
        "000000000000000000000000000000000000000000000000000000000000000000"
        "000000000000000000000000000000000000000000000000000000000b4c61756e"
        "63686e6f646573"
    )


def test_decoding_with_strict(collection, topics, log_data_missing_trailing_zeroes, ape_caplog):
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
