from pathlib import Path
from typing import Iterator, List

from dataclassy import dataclass
from pluggy import PluginManager  # type: ignore

from ape.api.accounts import AccountAPI, AccountContainerAPI
from ape.utils import cached_property, singledispatchmethod


@dataclass
class AccountManager:
    """
    Accounts is a container of containers for AccountAPI objects
    All containers must subclass AccountContainerAPI, and are treated as singletons
    """

    data_folder: Path
    plugin_manager: PluginManager
    # network_manager: NetworkManager

    @cached_property
    def account_containers(self) -> List[AccountContainerAPI]:
        containers = []
        self.data_folder.mkdir(exist_ok=True)
        for plugin_name, (container_type, account_type) in self.plugin_manager.account_types:
            accounts_folder = self.data_folder / plugin_name
            accounts_folder.mkdir(exist_ok=True)
            containers.append(container_type(accounts_folder, account_type))

        return containers

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

    @singledispatchmethod
    def __getitem__(self, account_id) -> AccountAPI:
        raise NotImplementedError("Cannot used " + type(account_id) + " as account id")

    @__getitem__.register
    def __getitem_int(self, account_id: int) -> AccountAPI:
        for idx, account in enumerate(self.__iter__()):
            if account_id == idx:
                # TODO: Inject `NetworkAPI` here
                return account

        raise IndexError(f"No account at index `{account_id}`.")

    @__getitem__.register
    def __getitem_str(self, account_id: str) -> AccountAPI:
        for container in self.account_containers:
            if account_id in container:
                # TODO: Inject `NetworkAPI` here
                return container[account_id]

        raise IndexError(f"No account with address `{account_id}`.")

    def __contains__(self, address: str) -> bool:
        return any(address in container for container in self.account_containers)
