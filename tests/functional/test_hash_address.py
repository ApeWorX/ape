import pytest

from ape.api.address import BaseAddress
from ape.types.address import AddressType


class TestAddress(BaseAddress):
    """Test implementation of BaseAddress with a configurable address value"""

    def __init__(self, address_value):
        self._address_value = address_value
        super().__init__()

    @property
    def address(self) -> AddressType:
        return self._address_value


@pytest.mark.parametrize(
    "address_input,expected_hash",
    [
        # String with 0x prefix
        (
            "0x1234567890123456789012345678901234567890",
            int("1234567890123456789012345678901234567890", 16),
        ),
        # String without 0x prefix
        (
            "1234567890123456789012345678901234567890",
            int("1234567890123456789012345678901234567890", 16),
        ),
        # Integer
        (123456789, 123456789),
        # Zero address
        ("0x0000000000000000000000000000000000000000", 0),
    ],
)
def test_hash_with_different_address_types(address_input, expected_hash):
    """Test hashing addresses of different types produces expected results"""
    address = TestAddress(address_input)
    # Test the actual __hash__ method directly to avoid Python's hash truncation
    assert address.__hash__() == expected_hash


def test_hash_with_hashstr20():
    """Test hashing with HashStr20-like object"""

    # Create a simple class that mimics HashStr20 behavior
    class TestHashStr20(str):
        def __str__(self):
            return self

    # Create an instance with a valid address string
    hash_str = TestHashStr20("0xabcdef1234567890abcdef1234567890abcdef12")

    address = TestAddress(hash_str)
    expected = int("abcdef1234567890abcdef1234567890abcdef12", 16)
    assert address.__hash__() == expected


def test_hash_with_hashbytes20():
    """Test hashing with HashBytes20-like object"""
    # Create bytes for address
    address_bytes = bytes.fromhex("1234567890123456789012345678901234567890")

    # Create a simple class that behaves like HashBytes20
    class TestHashBytes20(bytes):
        pass

    hash_bytes = TestHashBytes20(address_bytes)
    address = TestAddress(hash_bytes)

    expected = int.from_bytes(address_bytes, byteorder="big")
    assert address.__hash__() == expected


def test_hash_with_unsupported_type():
    """Test that TypeError is raised for unsupported address types"""
    address = TestAddress(None)
    with pytest.raises(TypeError, match="Cannot hash address of type"):
        address.__hash__()


def test_dict_key_equality():
    """Test that addresses with the same value but different types work as dict keys"""
    str_address = TestAddress("0x1234567890123456789012345678901234567890")
    int_address = TestAddress(int("1234567890123456789012345678901234567890", 16))

    assert str_address.__hash__() == int_address.__hash__()
    assert str_address == int_address

    test_dict = {str_address: "value"}
    assert int_address in test_dict
    assert test_dict[int_address] == "value"


def test_hash_is_consistent_with_equality():
    """Test that hash is consistent with equality for BaseAddress objects"""
    addr1 = TestAddress("0xabcdef1234567890abcdef1234567890abcdef12")
    addr2 = TestAddress("0xabcdef1234567890abcdef1234567890abcdef12")

    assert addr1 == addr2
    assert addr1.__hash__() == addr2.__hash__()
    assert hash(addr1) == hash(addr2)
    assert addr1.__hash__() != hash(addr1)

    # Test with set
    address_set = {addr1, addr2}
    assert len(address_set) == 1
