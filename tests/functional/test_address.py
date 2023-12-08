import pytest
from pydantic import BaseModel

from ape.api.address import BaseAddress
from ape.types import AddressType


@pytest.fixture
def custom_address(zero_address):
    class MyAddress(BaseAddress):
        @property
        def address(self) -> AddressType:
            return zero_address

    return MyAddress()


def test_eq(zero_address, custom_address):
    assert custom_address == zero_address
    assert zero_address == custom_address


def test_contains_in_list(zero_address, custom_address):
    assert zero_address in [custom_address]
    assert custom_address in [zero_address]


def test_address_type_in_model(zero_address):
    class CustomModel(BaseModel):
        address: AddressType

    model = CustomModel(address=zero_address)
    assert model.address == zero_address
