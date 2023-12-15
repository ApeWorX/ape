from collections import namedtuple
from typing import List

from eth_account import Account
from eth_account.hdaccount import HDPath
from eth_account.hdaccount.mnemonic import Mnemonic
from eth_pydantic_types import HexBytes

DEFAULT_NUMBER_OF_TEST_ACCOUNTS = 10
DEFAULT_TEST_MNEMONIC = "test test test test test test test test test test test junk"
DEFAULT_TEST_HD_PATH = "m/44'/60'/0'/0"
DEFAULT_TEST_CHAIN_ID = 1337
GeneratedDevAccount = namedtuple("GeneratedDevAccount", ("address", "private_key"))
"""
An account key-pair generated from the test mnemonic. Set the test mnemonic
in your ``ape-config.yaml`` file under the ``test`` section. Access your test
accounts using the :py:attr:`~ape.managers.accounts.AccountManager.test_accounts` property.

Config example::

    test:
      mnemonic: test test test test test test test test test test test junk
      number_of_accounts: 10

"""


def generate_dev_accounts(
    mnemonic: str = DEFAULT_TEST_MNEMONIC,
    number_of_accounts: int = DEFAULT_NUMBER_OF_TEST_ACCOUNTS,
    hd_path: str = DEFAULT_TEST_HD_PATH,
    start_index: int = 0,
) -> List[GeneratedDevAccount]:
    """
    Create accounts from the given test mnemonic.
    Use these accounts (or the mnemonic) in chain-genesis
    for testing providers.

    Args:
        mnemonic (str): mnemonic phrase or seed words.
        number_of_accounts (int): Number of accounts. Defaults to ``10``.
        hd_path(str): Hard Wallets/HD Keys derivation path format.
          Defaults to ``"m/44'/60'/0'/0"``.
        start_index (int): The index to start from in the path. Defaults
          to 0.

    Returns:
        List[:class:`~ape.utils.GeneratedDevAccount`]: List of development accounts.
    """
    seed = Mnemonic.to_seed(mnemonic)
    accounts = []

    if "{}" in hd_path or "{0}" in hd_path:
        hd_path_format = hd_path
    else:
        hd_path_format = f"{hd_path.rstrip('/')}/{{}}"

    for i in range(start_index, start_index + number_of_accounts):
        hd_path_obj = HDPath(hd_path_format.format(i))
        private_key = HexBytes(hd_path_obj.derive(seed)).hex()
        address = Account.from_key(private_key).address
        accounts.append(GeneratedDevAccount(address, private_key))

    return accounts
