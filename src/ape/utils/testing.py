from collections import namedtuple

from eth_account import Account
from eth_account.hdaccount import HDPath
from eth_account.hdaccount.mnemonic import Mnemonic
from eth_utils import to_hex

DEFAULT_NUMBER_OF_TEST_ACCOUNTS = 10
DEFAULT_TEST_MNEMONIC = "test test test test test test test test test test test junk"
DEFAULT_TEST_HD_PATH = "m/44'/60'/0'/0"
DEFAULT_TEST_CHAIN_ID = 1337
DEFAULT_TEST_ACCOUNT_BALANCE = int(10e21)  # 10,000 Ether (in Wei)
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
) -> list[GeneratedDevAccount]:
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
        list[:class:`~ape.utils.GeneratedDevAccount`]: List of development accounts.
    """
    seed = Mnemonic.to_seed(mnemonic)
    hd_path_format = (
        hd_path if "{}" in hd_path or "{0}" in hd_path else f"{hd_path.rstrip('/')}/{{}}"
    )
    return [
        _generate_dev_account(hd_path_format, i, seed)
        for i in range(start_index, start_index + number_of_accounts)
    ]


def _generate_dev_account(hd_path, index: int, seed: bytes) -> GeneratedDevAccount:
    return GeneratedDevAccount(
        address=Account.from_key(
            private_key := to_hex(HDPath(hd_path.format(index)).derive(seed))
        ).address,
        private_key=private_key,
    )
