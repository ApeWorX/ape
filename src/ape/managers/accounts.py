import contextlib
from collections.abc import Generator, Iterator
from contextlib import AbstractContextManager as ContextManager
from functools import cached_property, singledispatchmethod
from typing import Optional, Union

from eth_utils import is_hex

from ape.api.accounts import (
    AccountAPI,
    AccountContainerAPI,
    ImpersonatedAccount,
    TestAccountAPI,
    TestAccountContainerAPI,
)
from ape.exceptions import AccountsError, ConversionError
from ape.managers.base import BaseManager
from ape.types.address import AddressType
from ape.utils.basemodel import ManagerAccessMixin
from ape.utils.misc import log_instead_of_fail

_DEFAULT_SENDERS: list[AccountAPI] = []


@contextlib.contextmanager
def _use_sender(
    account: Union[AccountAPI, TestAccountAPI]
) -> Generator[AccountAPI, TestAccountAPI, None]:
    try:
        _DEFAULT_SENDERS.append(account)
        yield account
    finally:
        _DEFAULT_SENDERS.pop()


class TestAccountManager(list, ManagerAccessMixin):
    __test__ = False

    _impersonated_accounts: dict[AddressType, ImpersonatedAccount] = {}
    _accounts_by_index: dict[int, AccountAPI] = {}

    @log_instead_of_fail(default="<TestAccountManager>")
    def __repr__(self) -> str:
        accounts_str = ", ".join([a.address for a in self.accounts])
        return f"[{accounts_str}]"

    @cached_property
    def containers(self) -> dict[str, TestAccountContainerAPI]:
        account_types = filter(
            lambda t: issubclass(t[1][1], TestAccountAPI), self.plugin_manager.account_types
        )
        return {
            plugin_name: container_type(name=plugin_name, account_type=account_type)
            for plugin_name, (container_type, account_type) in account_types
        }

    @property
    def accounts(self) -> Iterator[AccountAPI]:
        for container in self.containers.values():
            yield from container.accounts

    def aliases(self) -> Iterator[str]:
        for account in self.accounts:
            if account.alias:
                yield account.alias

    def __len__(self) -> int:
        return sum(len(c) for c in self.containers.values())

    def __iter__(self) -> Iterator[AccountAPI]:
        yield from self.accounts

    @singledispatchmethod
    def __getitem__(self, account_id):
        raise NotImplementedError(f"Cannot use {type(account_id)} as account ID.")

    @__getitem__.register
    def __getitem_int(self, account_id: int):
        if account_id in self._accounts_by_index:
            return self._accounts_by_index[account_id]

        original_account_id = account_id
        if account_id < 0:
            account_id = len(self) + account_id

        account = self.containers["test"].get_test_account(account_id)
        self._accounts_by_index[original_account_id] = account
        return account

    @__getitem__.register
    def __getitem_slice(self, account_id: slice):
        start_idx = account_id.start or 0
        if start_idx < 0:
            start_idx += len(self)
        stop_idx = account_id.stop or len(self)
        if stop_idx < 0:
            stop_idx += len(self)
        step_size = account_id.step or 1
        return [self[i] for i in range(start_idx, stop_idx, step_size)]

    @__getitem__.register
    def __getitem_str(self, account_str: str):
        message_fmt = "No account with {} '{}'."
        try:
            account_id = self.conversion_manager.convert(account_str, AddressType)
        except ConversionError as err:
            message = message_fmt.format("ID", account_str)
            raise KeyError(message) from err

        for account in self.accounts:
            if account.address == account_id:
                return account

        try:
            return self.impersonate_account(account_id)
        except AccountsError as err:
            err_message = message_fmt.format("address", account_id)
            raise KeyError(f"{str(err).rstrip('.')}:\n{err_message}") from err

    def __contains__(self, address: AddressType) -> bool:  # type: ignore
        return any(address in container for container in self.containers.values())

    def impersonate_account(self, address: AddressType) -> ImpersonatedAccount:
        """
        Impersonate an account for testing purposes.

        Args:
            address (AddressType): The address to impersonate.
        """
        try:
            result = self.provider.unlock_account(address)
        except NotImplementedError as err:
            raise AccountsError("Your provider does not support impersonating accounts.") from err

        if result:
            if address in self._impersonated_accounts:
                return self._impersonated_accounts[address]

            account = ImpersonatedAccount(raw_address=address)
            self._impersonated_accounts[address] = account
            return account

        raise AccountsError(f"Unable to unlocked account '{address}'.")

    def stop_impersonating(self, address: AddressType):
        """
        End the impersonating of an account, if it is being impersonated.

        Args:
            address (AddressType): The address to stop impersonating.
        """
        if address in self._impersonated_accounts:
            del self._impersonated_accounts[address]

        try:
            self.provider.relock_account(address)
        except NotImplementedError:
            pass

    def generate_test_account(self, container_name: str = "test") -> TestAccountAPI:
        return self.containers[container_name].generate_account()

    def use_sender(self, account_id: Union[TestAccountAPI, AddressType, int]) -> ContextManager:
        account = account_id if isinstance(account_id, TestAccountAPI) else self[account_id]
        return _use_sender(account)

    def init_test_account(
        self, index: int, address: AddressType, private_key: str
    ) -> "TestAccountAPI":
        container = self.containers["test"]
        return container.init_test_account(  # type: ignore[attr-defined]
            index, address, private_key
        )

    def reset(self):
        self._accounts_by_index = {}
        for container in self.containers.values():
            container.reset()


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

    _alias_to_account_cache: dict[str, AccountAPI] = {}

    @property
    def default_sender(self) -> Optional[AccountAPI]:
        return _DEFAULT_SENDERS[-1] if _DEFAULT_SENDERS else None

    @cached_property
    def containers(self) -> dict[str, AccountContainerAPI]:
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

            containers[plugin_name] = container_type(name=plugin_name, account_type=account_type)

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

    def get_accounts_by_type(self, type_: type[AccountAPI]) -> list[AccountAPI]:
        """
        Get a list of accounts by their type.

        Args:
            type_ (type[:class:`~ape.api.accounts.AccountAPI`]): The type of account
              to get.

        Returns:
            list[:class:`~ape.api.accounts.AccountAPI`]
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
            yield from container.accounts

    @log_instead_of_fail(default="<AccountManager>")
    def __repr__(self) -> str:
        return "[" + ", ".join(repr(a) for a in self) + "]"

    @cached_property
    def test_accounts(self) -> TestAccountManager:
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
            :class:`TestAccountContainer`
        """
        return TestAccountManager()

    def load(self, alias: str) -> AccountAPI:
        """
        Get an account by its alias.

        Raises:
            KeyError: When there is no local account with the given alias.

        Returns:
            :class:`~ape.api.accounts.AccountAPI`
        """
        if alias == "":
            raise ValueError("Cannot use empty string as alias!")

        elif alias in self._alias_to_account_cache:
            return self._alias_to_account_cache[alias]

        for account in self:
            if account.alias and account.alias == alias:
                self._alias_to_account_cache[alias] = account
                return account

        raise KeyError(f"No account with alias '{alias}'.")

    @singledispatchmethod
    def __getitem__(self, account_id) -> AccountAPI:
        raise NotImplementedError(f"Cannot use {type(account_id)} as account ID.")

    @__getitem__.register
    def __getitem_int(self, account_id: int) -> AccountAPI:
        """
        Get an account by index. For example, when you do the CLI command
        ``ape accounts list --all``, you will see a list of enumerated accounts
        by their indices. Use this method as a quicker, ad-hoc way to get an
        account from that index.

        **NOTE**: It is generally preferred to use
        :meth:`~ape.managers.accounts.AccountManager.load` or
        :meth:`~ape.managers.accounts.AccountManager.__getitem_str`.

        Returns:
            :class:`~ape.api.accounts.AccountAPI`
        """
        if account_id < 0:
            account_id = len(self) + account_id
        for idx, account in enumerate(self):
            if account_id == idx:
                return account

        raise IndexError(f"No account at index '{account_id}'.")

    @__getitem__.register
    def __getitem_slice(self, account_id: slice):
        """
        Get list of accounts by slice. For example, when you do the CLI command
        ``ape accounts list --all``, you will see a list of enumerated accounts
        by their indices. Use this method as a quicker, ad-hoc way to get an
        accounts from a slice.

        **NOTE**: It is generally preferred to use
        :meth:`~ape.managers.accounts.AccountManager.load` or
        :meth:`~ape.managers.accounts.AccountManager.__getitem_str`.

        Returns:
            list[:class:`~ape.api.accounts.AccountAPI`]
        """

        start_idx = account_id.start or 0
        if start_idx < 0:
            start_idx += len(self)
        stop_idx = account_id.stop or len(self)
        if stop_idx < 0:
            stop_idx += len(self)
        step_size = account_id.step or 1
        return [self[i] for i in range(start_idx, stop_idx, step_size)]

    @__getitem__.register
    def __getitem_str(self, account_str: str) -> AccountAPI:
        """
        Get an account by address. If we are using a provider that supports unlocking
        accounts, this method will return an impersonated account at that address.

        Raises:
            KeyError: When there is no local account with the given address.

        Returns:
            :class:`~ape.api.accounts.AccountAPI`
        """

        try:
            account_id = self.conversion_manager.convert(account_str, AddressType)
        except ConversionError as err:
            prefix = f"No account with ID '{account_str}'"
            if account_str.endswith(".eth"):
                suffix = "Do you have `ape-ens` installed?"
            else:
                suffix = "Do you have the necessary conversion plugins installed?"

            raise KeyError(f"{prefix}. {suffix}") from err

        for container in self.containers.values():
            if account_id in container.accounts:
                return container[account_id]

        # NOTE: Fallback to `TestAccountContainer`'s method for loading items
        return self.test_accounts[account_id]

    def __contains__(self, address: AddressType) -> bool:
        """
        Determine if the given address matches an account in ``ape``.

        Args:
            address (:class:`~ape.types.address.AddressType`): The address to check.

        Returns:
            bool: ``True`` when the given address is found.
        """
        return (
            any(address in container for container in self.containers.values())
            or address in self.test_accounts
        )

    def use_sender(
        self,
        account_id: Union[AccountAPI, AddressType, str, int],
    ) -> ContextManager:
        if not isinstance(account_id, AccountAPI):
            if isinstance(account_id, int) or is_hex(account_id):
                account = self[account_id]
            elif isinstance(account_id, str):  # alias
                account = self.load(account_id)
            else:
                raise TypeError(account_id)
        else:
            account = account_id

        return _use_sender(account)

    def init_test_account(
        self, index: int, address: AddressType, private_key: str
    ) -> "TestAccountAPI":
        return self.test_accounts.init_test_account(index, address, private_key)
