from typing import Any

import pytest

from ape.api.convert import ConvertibleAPI
from ape.types.address import AddressType


@pytest.fixture(scope="module")
def custom_type(accounts):
    class MyAccountWrapper(ConvertibleAPI):
        def __init__(self, acct):
            self.acct = acct

        def is_convertible(self, to_type: type) -> bool:
            return to_type is AddressType

        def convert_to(self, to_type: type) -> Any:
            if to_type is AddressType:
                return self.acct.address

            raise NotImplementedError()

    return MyAccountWrapper(accounts[0])


def test_convert(custom_type, conversion_manager, accounts):
    """
    You can use the regular conversion manager to convert the custom type.
    """
    actual = conversion_manager.convert(custom_type, AddressType)
    assert actual == accounts[0].address
