from datetime import datetime, timedelta, timezone

import pytest

from ape import convert
from ape.exceptions import ConversionError


@pytest.mark.parametrize(
    "args",
    (
        [
            "10-15-2021 12:15:12",
            "2021-10-15 12:15:12",
            "15-10-2021 12:15:12",
            datetime.fromisoformat("2021-10-15 12:15:12"),
        ]
    ),
)
def test_convert_string_timestamp(args):
    assert convert(args, int) == 1634300112


@pytest.mark.parametrize(
    "args",
    (
        [
            "0000",
            "2003",
            "9999999999",
            "2001-01-01 12:15:12 123",
        ]
    ),
)
def test_convert_string_bad_timestamp(args):
    with pytest.raises(ConversionError):
        convert(args, int)


def test_convert_timedelta_timestamp():
    delta = timedelta(days=2, hours=2, minutes=12)
    assert convert(delta, int) == int((datetime.now(timezone.utc) + delta).timestamp())
