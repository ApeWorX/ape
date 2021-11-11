from typing import Dict, Iterator, List, Type

from dataclassy import dataclass
from pluggy import PluginManager  # type: ignore

from ape.api.accounts import AccountAPI, AccountContainerAPI, TestAccountAPI
from ape.types import AddressType
from ape.utils import cached_property, singledispatchmethod

from .config import ConfigManager
from .converters import ConversionManager
from .networks import NetworkManager


@dataclass
class AccountManager:
    """
    Accounts is a container of containers for AccountAPI objects
    All containers must subclass AccountContainerAPI, and are treated as singletons
    """

    config: ConfigManager
    converters: ConversionManager
    plugin_manager: PluginManager
    network_manager: NetworkManager

    @cached_property
    def containers(self) -> Dict[str, AccountContainerAPI]:
        containers = {}
        data_folder = self.config.DATA_FOLDER
        data_folder.mkdir(exist_ok=True)
        for plugin_name, (container_type, account_type) in self.plugin_manager.account_types:

            # Ignore containers that contain test accounts.
            if issubclass(account_type, TestAccountAPI):
                continue

            accounts_folder = data_folder / plugin_name
            accounts_folder.mkdir(exist_ok=True)
            containers[plugin_name] = container_type(accounts_folder, account_type, self.config)

        return containers

    @property
    def aliases(self) -> Iterator[str]:
        for container in self.containers.values():
            yield from container.aliases

    def get_accounts_by_type(self, type_: Type[AccountAPI]) -> List[AccountAPI]:
        accounts_with_type = []
        for account in self:
            if isinstance(account, type_):
                self._inject_provider(account)
                accounts_with_type.append(account)

        return accounts_with_type

    def __len__(self) -> int:
        return sum(len(container) for container in self.containers.values())

    def __iter__(self) -> Iterator[AccountAPI]:
        for container in self.containers.values():
            for account in container:
                self._inject_provider(account)
                yield account

    def __repr__(self) -> str:
        return "[" + ", ".join(repr(a) for a in self) + "]"

    @cached_property
    def test_accounts(self) -> List[TestAccountAPI]:
        """
        Accounts generated from the configured test mnemonic.
        Use these accounts when testing.
        """
        accounts = []
        for plugin_name, (container_type, account_type) in self.plugin_manager.account_types:
            if not issubclass(account_type, TestAccountAPI):
                continue

            container = container_type(None, account_type, self.config)
            for account in container:
                self._inject_provider(account)
                accounts.append(account)

        return accounts

    def load(self, alias: str) -> AccountAPI:
        if alias == "":
            raise ValueError("Cannot use empty string as alias!")

        for account in self:
            if account.alias and account.alias == alias:
                self._inject_provider(account)
                return account

        raise IndexError(f"No account with alias `{alias}`.")

    @singledispatchmethod
    def __getitem__(self, account_id) -> AccountAPI:
        raise NotImplementedError(f"Cannot use {type(account_id)} as account ID.")

    @__getitem__.register
    def __getitem_int(self, account_id: int) -> AccountAPI:
        for idx, account in enumerate(self.__iter__()):
            if account_id == idx:
                self._inject_provider(account)
                return account

        raise IndexError(f"No account at index `{account_id}`.")

    @__getitem__.register
    def __getitem_str(self, account_str: str) -> AccountAPI:
        account_id = self.converters.convert(account_str, AddressType)

        for container in self.containers.values():
            if account_id in container:
                account = container[account_id]
                self._inject_provider(account)
                return account

        raise IndexError(f"No account with address `{account_id}`.")

    def __contains__(self, address: AddressType) -> bool:
        return any(address in container for container in self.containers.values())

    def _inject_provider(self, account: AccountAPI):
        if self.network_manager.active_provider is not None:
            account.provider = self.network_manager.active_provider
