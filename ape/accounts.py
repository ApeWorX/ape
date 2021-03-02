from typing import Iterator, List

from ape.plugins.account_api import AccountAPI, AccountContainerAPI

# NOTE: This class is an aggregated container for all of the registered containers
class Accounts(AccountContainerAPI):
    def __init__(self):
        # NOTE: Delayed loading of cached accounts (prevents circular imports)
        self._account_plugins: List[AccountContainerAPI] = None

    @property
    def account_plugins(self) -> Iterator[AccountContainerAPI]:
        if not self._account_plugins:
            from ape import plugins

            account_plugins = plugins.registered_plugins[plugins.AccountPlugin]
            self._account_plugins = [p.data() for p in account_plugins]

        for container in self._account_plugins:
            yield container

    @property
    def aliases(self) -> Iterator[str]:
        for container in self.account_plugins:
            for alias in container.aliases:
                yield alias

    def __len__(self) -> int:
        return sum(len(container) for container in self.account_plugins)

    def __iter__(self) -> Iterator[AccountAPI]:
        for container in self.account_plugins:
            for account in container:
                # TODO: Inject Web3
                yield account

    def load(self, alias: str) -> AccountAPI:
        if alias == "":
            raise ValueError("Cannot use empty string as alias!")

        for account in self:
            if account.alias == alias:
                return account

        raise IndexError(f"No account with alias `{alias}`.")

    def __getitem__(self, address: str) -> AccountAPI:
        for container in self.account_plugins:
            if address in container:
                return container[address]

        raise IndexError(f"No account with address `{address}`.")

    def __contains__(self, address: str) -> bool:
        return any(address in container for container in self.account_plugins)


accounts = Accounts()
