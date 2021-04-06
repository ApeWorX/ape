try:
    from functools import cached_property
except ImportError:
    from backports.cached_property import cached_property  # type: ignore

from typing import Iterator, List

from dataclassy import dataclass
from pluggy import PluginManager  # type: ignore

from ape.api.accounts import AccountAPI, AccountContainerAPI


@dataclass
class AccountManager:
    """
    Accounts is a container of containers for AccountAPI objects
    All containers must subclass AccountContainerAPI, and are treated as singletons
    """

    plugin_manager: PluginManager
    # network_manager: NetworkManager

    @cached_property
    def account_containers(self) -> List[AccountContainerAPI]:
        from ape import DATA_FOLDER

        accounts_folder = DATA_FOLDER / "accounts"  # TODO: Use plugin name
        accounts_folder.mkdir(exist_ok=True)
        return [
            container_type(accounts_folder, account_type)
            for container_type, account_type in self.plugin_manager.hook.account_types()
        ]

    @property
    def aliases(self) -> Iterator[str]:
        for container in self.account_containers:
            for alias in container.aliases:
                yield alias

    def __len__(self) -> int:
        return sum(len(container) for container in self.account_containers)

    def __iter__(self) -> Iterator[AccountAPI]:
        for container in self.account_containers:
            for account in container:
                # TODO: Inject `NetworkAPI` here
                yield account

    def load(self, alias: str) -> AccountAPI:
        if alias == "":
            raise ValueError("Cannot use empty string as alias!")

        for account in self:
            if account.alias and account.alias == alias:
                # TODO: Inject `NetworkAPI` here
                return account

        raise IndexError(f"No account with alias `{alias}`.")

    def __getitem__(self, account_id) -> AccountAPI:
        for container in self.account_containers:
            if account_id in container:
                # TODO: Inject `NetworkAPI` here
                return container[account_id]

        raise IndexError(f"No account with address `{account_id}`.")

    def __contains__(self, address: str) -> bool:
        return any(address in container for container in self.account_containers)
