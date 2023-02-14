from collections import namedtuple
from typing import List

from eth_account import Account
from eth_account.hdaccount import HDPath
from eth_account.hdaccount.mnemonic import Mnemonic
from hexbytes import HexBytes

DEFAULT_NUMBER_OF_TEST_ACCOUNTS = 10
DEFAULT_TEST_MNEMONIC = "test test test test test test test test test test test junk"
DEFAULT_HD_PATH = "m/44'/60'/0'/{}"
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
    hd_path_format: str = DEFAULT_HD_PATH,
    start_index: int = 0,
) -> List[GeneratedDevAccount]:
    """
    Create accounts from the given test mnemonic.
    Use these accounts (or the mnemonic) in chain-genesis
    for testing providers.

    Args:
        mnemonic (str): mnemonic phrase or seed words.
        number_of_accounts (int): Number of accounts. Defaults to ``10``.
        hd_path_format (str): Hard Wallets/HD Keys derivation path format.
          Defaults to ``"m/44'/60'/0'/0/{}"``.

    Returns:
        List[:class:`~ape.utils.GeneratedDevAccount`]: List of development accounts.
    """
    seed = Mnemonic.to_seed(mnemonic)
    accounts = []

    for i in range(start_index, start_index + number_of_accounts):
        hd_path = HDPath(hd_path_format.format(i))
        private_key = HexBytes(hd_path.derive(seed)).hex()
        address = Account.from_key(private_key).address
        accounts.append(GeneratedDevAccount(address, private_key))

    return accounts
