from typing import Iterator, List

from ape.plugins.account_api import AccountAPI, AccountContainerAPI

# NOTE: This class is an aggregated container for all of the registered containers
class Accounts(AccountContainerAPI):
    def __init__(self):
        # NOTE: Delayed loading of cached accounts (prevents circular imports)
        self._all_accounts = None

    @property
    def all_accounts(self):
        if not self._all_accounts:
            from ape import plugins

            account_plugins = plugins.registered_plugins[plugins.AccountPlugin]
            self._all_accounts = [p.data() for p in account_plugins]

        return self._all_accounts

    @property
    def aliases(self) -> List[str]:
        aliases = []
        for accounts in self.all_accounts:
            aliases += accounts.aliases

        return aliases

    def __len__(self) -> int:
        return sum(len(accounts) for accounts in self.all_accounts)

    def __iter__(self) -> Iterator[AccountAPI]:
        for accounts in self.all_accounts:
            for account in accounts:
                # TODO: Inject Web3
                yield account

    def load(self, alias: str) -> AccountAPI:
        if alias == "":
            raise ValueError("Cannot use empty string as alias!")

        for account in self:
            if account.alias == alias:
                # TODO: Inject Web3
                return account

        raise IndexError(f"No account with alias `{alias}`.")

    def __getitem__(self, address: str) -> AccountAPI:
        for account in self:
            if address == account.address:
                # TODO: Inject Web3
                return account

        raise IndexError(f"No account with address `{address}`.")

    def __contains__(self, address: str) -> bool:
        return any(address in accounts for accounts in self.all_accounts)


accounts = Accounts()
