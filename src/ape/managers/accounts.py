from typing import Dict, Iterator, List, Type

from ape.api.accounts import AccountAPI, AccountContainerAPI, TestAccountAPI
from ape.types import AddressType
from ape.utils import cached_property, singledispatchmethod

from .base import BaseManager


class AccountManager(BaseManager):
    """
    The ``AccountManager`` is a container of containers for
    :class:`~ape.api.accounts.AccountAPI` objects.
    All containers must subclass :class:`~ape.api.accounts.AccountContainerAPI`
    and are treated as singletons.

    Import the accounts manager singleton from the root ``ape`` namespace.

    Usage example::

        from ape import accounts  # "accounts" is the AccountManager singleton

        my_accounts = accounts.load("dev")
    """

    @cached_property
    def containers(self) -> Dict[str, AccountContainerAPI]:
        """
        A dict of all :class:`~ape.api.accounts.AccountContainerAPI` instances
        across all installed plugins.

        Returns:
            dict[str, :class:`~ape.api.accounts.AccountContainerAPI`]
        """

        containers = {}
        data_folder = self.config_manager.DATA_FOLDER
        data_folder.mkdir(exist_ok=True)
        for plugin_name, (container_type, account_type) in self.plugin_manager.account_types:

            # Ignore containers that contain test accounts.
            if issubclass(account_type, TestAccountAPI):
                continue

            accounts_folder = data_folder / plugin_name
            accounts_folder.mkdir(exist_ok=True)
            containers[plugin_name] = container_type(
                data_folder=accounts_folder, account_type=account_type
            )

        return containers

    @property
    def aliases(self) -> Iterator[str]:
        """
        All account aliases from every account-related plugin. The "alias"
        is part of the :class:`~ape.api.accounts.AccountAPI`. Use the
        account alias to load an account using method
        :meth:`~ape.managers.accounts.AccountManager.load`.

        Returns:
            Iterator[str]
        """

        for container in self.containers.values():
            yield from container.aliases

    def get_accounts_by_type(self, type_: Type[AccountAPI]) -> List[AccountAPI]:
        """
        Get a list of accounts by their type.

        Args:
            type_ (Type[:class:`~ape.api.accounts.AccountAPI`]): The type of account
              to get.

        Returns:
            List[:class:`~ape.api.accounts.AccountAPI`]
        """

        return [acc for acc in self if isinstance(acc, type_)]

    def __len__(self) -> int:
        """
        The number of accounts managed by all account plugins.

        Returns:
            int
        """

        return sum(len(container) for container in self.containers.values())

    def __iter__(self) -> Iterator[AccountAPI]:
        for container in self.containers.values():
            for account in container.accounts:
                yield account  # type: ignore

    def __repr__(self) -> str:
        return "[" + ", ".join(repr(a) for a in self) + "]"

    @cached_property
    def test_accounts(self) -> List[TestAccountAPI]:
        """
        Accounts generated from the configured test mnemonic. These accounts
        are also the subject of a fixture available in the ``test`` plugin called
        ``accounts``. Configure these accounts, such as the mnemonic and / or
        number-of-accounts using the ``test`` section of the `ape-config.yaml` file.

        Usage example::

            def test_my_contract(accounts):
               # The "accounts" fixture uses the AccountsManager.test_accounts()
               sender = accounts[0]
               receiver = accounts[1]
               ...

        Returns:
            List[:class:`~ape.api.accounts.TestAccountAPI`]
        """
        accounts = []
        for plugin_name, (container_type, account_type) in self.plugin_manager.account_types:
            if not issubclass(account_type, TestAccountAPI):
                continue

            # pydantic validation won't allow passing None for data_folder/required attr
            container = container_type(data_folder="", account_type=account_type)
            accounts.extend([acc for acc in container.accounts])

        return accounts

    def load(self, alias: str) -> AccountAPI:
        """
        Get an account by its alias.

        Raises:
            IndexError: When there is no local account with the given alias.

        Returns:
            :class:`~ape.api.accounts.AccountAPI`
        """

        if alias == "":
            raise ValueError("Cannot use empty string as alias!")

        for account in self:
            if account.alias and account.alias == alias:
                return account

        raise IndexError(f"No account with alias '{alias}'.")

    @singledispatchmethod
    def __getitem__(self, account_id) -> AccountAPI:
        raise NotImplementedError(f"Cannot use {type(account_id)} as account ID.")

    @__getitem__.register
    def __getitem_int(self, account_id: int) -> AccountAPI:
        """
        Get an account by index. For example, when you do the CLI command
        ``ape accounts list --all``, you will see a list of enumerated accounts
        by their indices. Use this method as a quicker, ad-hoc way to get an
        account from that index. **NOTE**: It is generally preferred to use
        :meth:`~ape.managers.accounts.AccountManager.load` or
        :meth:`~ape.managers.accounts.AccountManager.__getitem_str`.

        Returns:
            :class:`~ape.api.accounts.AccountAPI`
        """

        for idx, account in enumerate(self):
            if account_id == idx:
                return account

        raise IndexError(f"No account at index '{account_id}'.")

    @__getitem__.register
    def __getitem_str(self, account_str: str) -> AccountAPI:
        """
        Get an account by address.

        Raises:
            IndexError: When there is no local account with the given address.

        Returns:
            :class:`~ape.api.accounts.AccountAPI`
        """

        account_id = self.conversion_manager.convert(account_str, AddressType)

        for container in self.containers.values():
            if account_id in container.accounts:
                return container[account_id]

        raise IndexError(f"No account with address '{account_id}'.")

    def __contains__(self, address: AddressType) -> bool:
        """
        Determine if the given address matches an account in ``ape``.

        Args:
            address (``AddressType``): The address to check.

        Returns:
            bool: ``True`` when the given address is found.
        """

        return any(address in container for container in self.containers.values())
