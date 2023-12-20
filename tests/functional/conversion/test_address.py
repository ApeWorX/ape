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
