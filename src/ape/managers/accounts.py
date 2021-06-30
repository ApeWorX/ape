from typing import Dict, Iterator

from dataclassy import dataclass
from pluggy import PluginManager  # type: ignore

from ape.api.accounts import AccountAPI, AccountContainerAPI
from ape.utils import cached_property, singledispatchmethod

from .config import ConfigManager
from .networks import NetworkManager


@dataclass
class AccountManager:
    """
    Accounts is a container of containers for AccountAPI objects
    All containers must subclass AccountContainerAPI, and are treated as singletons
    """

    config: ConfigManager
    plugin_manager: PluginManager
    network_manager: NetworkManager

    @cached_property
    def containers(self) -> Dict[str, AccountContainerAPI]:
        containers = dict()
        data_folder = self.config.DATA_FOLDER
        data_folder.mkdir(exist_ok=True)
        for plugin_name, (container_type, account_type) in self.plugin_manager.account_types:
            accounts_folder = data_folder / plugin_name
            accounts_folder.mkdir(exist_ok=True)
            containers[plugin_name] = container_type(accounts_folder, account_type)

        return containers

    @property
    def aliases(self) -> Iterator[str]:
        for container in self.containers.values():
            for alias in container.aliases:
                yield alias

    def __len__(self) -> int:
        return sum(len(container) for container in self.containers.values())

    def __iter__(self) -> Iterator[AccountAPI]:
        for container in self.containers.values():
            for account in container:
                # NOTE: Inject provider
                account._provider = self.network_manager.active_provider
                yield account

    def load(self, alias: str) -> AccountAPI:
        if alias == "":
            raise ValueError("Cannot use empty string as alias!")

        for account in self:
            if account.alias and account.alias == alias:
                # NOTE: Inject provider
                account._provider = self.network_manager.active_provider
                return account

        raise IndexError(f"No account with alias `{alias}`.")

    @singledispatchmethod
    def __getitem__(self, account_id) -> AccountAPI:
        raise NotImplementedError("Cannot use " + type(account_id) + " as account id")

    @__getitem__.register
    def __getitem_int(self, account_id: int) -> AccountAPI:
        for idx, account in enumerate(self.__iter__()):
            if account_id == idx:
                # NOTE: Inject provider
                account._provider = self.network_manager.active_provider
                return account

        raise IndexError(f"No account at index `{account_id}`.")

    @__getitem__.register
    def __getitem_str(self, account_id: str) -> AccountAPI:
        for container in self.containers.values():
            if account_id in container:
                account = container[account_id]
                # NOTE: Inject provider
                account._provider = self.network_manager.active_provider
                return account

        raise IndexError(f"No account with address `{account_id}`.")

    def __contains__(self, address: str) -> bool:
        return any(address in container for container in self.containers.values())
