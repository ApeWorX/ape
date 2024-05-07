from eth_typing import ChecksumAddress, HexAddress, HexStr

from ape.types import AddressType


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


def test_convert_address_missing_padding_to_int(convert, owner):
    # NOTE: Should be "0x0f135c529caf5abb89156b3adaa7732eace9eb0f"
    address_str = HexStr("0xf135c529caf5abb89156b3adaa7732eace9eb0f")
    address_missing_padded_zero = ChecksumAddress(HexAddress(address_str))
    actual = convert(address_missing_padded_zero, int)
    assert actual == 0xf135c529caf5abb89156b3adaa7732eace9eb0f
