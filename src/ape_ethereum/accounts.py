from typing import Optional

from eth_account import Account

from ape.api.accounts import AccountAPI
from ape.api.transactions import TransactionAPI


class EthAccount(AccountAPI):
    """
    A simple, non-registered Ape account API that wraps an ``eth_account.Account``.
    """

    inner: Account

    def sign_transaction(self, txn: TransactionAPI, **signer_options) -> Optional[TransactionAPI]:
        return self.inner.sign_transaction(txn, **signer_options)
