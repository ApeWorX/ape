from ape import Contract
from ape.api import Address


def test_init_at_unknown_address():
    address = "0x274b028b03A250cA03644E6c578D81f019eE1323"
    contract = Contract(address)
    assert type(contract) == Address
    assert contract.address == address
