from typing import Any

import base58
import pytest
from pydantic import BaseModel

from ape.api import ConverterAPI
from ape.managers.converters import HexAddressConverter, IntAddressConverter
from ape.types.address import AddressType


class Base58AddressConverter(ConverterAPI):
    """
    A Solana-style converter for base58-encoded 32-byte public keys.
    """

    def is_convertible(self, value: Any) -> bool:
        if not isinstance(value, str) or value.startswith("0x"):
            return False

        try:
            return len(base58.b58decode(value)) == 32
        except ValueError:
            return False

    def convert(self, value: str) -> str:
        return value


@pytest.fixture
def base58_address_converter(conversion_manager):
    address_converters = conversion_manager._converters[AddressType]
    converter = Base58AddressConverter()
    address_converters.append(converter)
    yield converter
    address_converters.remove(converter)


def test_convert_keyfile_account_to_address(convert, keyfile_account):
    actual = convert(keyfile_account, AddressType)
    assert actual == keyfile_account.address


def test_convert_test_account_to_address(convert, owner):
    actual = convert(owner, AddressType)
    assert actual == owner.address


def test_convert_address_to_int(convert, owner):
    actual = convert(owner.address, int)
    assert actual == int(owner.address, 16)


def test_convert_account_to_int(convert, owner):
    actual = convert(owner, int)
    assert actual == int(owner.address, 16)


def test_convert_0_to_address(convert, zero_address):
    assert convert(0, AddressType) == zero_address


def test_address_type_non_evm_address(base58_address_converter):
    class Transfer(BaseModel):
        receiver: AddressType

    solana_address = base58.b58encode(bytes(range(32))).decode()

    assert Transfer(receiver=solana_address).receiver == solana_address


class TestHexAddressConverter:
    @pytest.fixture(scope="class")
    def converter(self):
        return HexAddressConverter()

    def test_is_convertible_hex_str(self, converter):
        assert not converter.is_convertible("0x123")

    def test_is_convertible_address(self, converter, owner):
        # Is already an address!
        assert not converter.is_convertible(str(owner.address))

    def test_convert_not_canonical_address(self, converter):
        actual = converter.convert("0x0ffffffaaaaaaaabbbbbbb333337777eeeeeee00")
        expected = "0x0fFFfffAaAaAaAaBBBbBbb333337777eeeeeEe00"
        assert actual == expected


class TestIntAddressConverter:
    @pytest.fixture(scope="class")
    def converter(self):
        return IntAddressConverter()

    def test_is_convertible(self, converter, owner):
        int_address = int(owner.address, 16)
        assert converter.is_convertible(int_address)

    def test_is_convertible_random_int(self, converter):
        assert converter.is_convertible(0)

    @pytest.mark.parametrize("val", (0, 1))
    def test_convert_simple_int(self, converter, val, zero_address):
        actual = converter.convert(val)
        expected = f"{zero_address[:-1]}{val}"
        assert actual == expected
