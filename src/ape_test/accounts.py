from collections.abc import Iterator
from functools import cached_property
from typing import Optional, cast

from ape.api.accounts import TestAccountAPI, TestAccountContainerAPI
from ape.exceptions import ProviderNotConnectedError
from ape.types import AddressType
from ape.utils.misc import log_instead_of_fail
from ape.utils.testing import generate_dev_accounts
from ape_accounts.accounts import ApeSigner


class TestAccountContainer(TestAccountContainerAPI):
    generated_accounts: list["TestAccount"] = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def __len__(self) -> int:
        return self.number_of_accounts + len(self.generated_accounts)

    @property
    def mnemonic(self) -> str:
        # Overridden so we can overload the setter.
        return self.config_manager.test.mnemonic

    @mnemonic.setter
    def mnemonic(self, mnemonic: str) -> None:
        # Overridden so we can also clear out generated accounts cache.
        self.config_manager.test.mnemonic = mnemonic
        self.generated_accounts = []

    @mnemonic.setter
    def mnemonic(self, mnemonic: str) -> None:
        self.config_manager.test.mnemonic = mnemonic
        self.generated_accounts = []

    @property
    def config(self):
        return self.config_manager.get_config("test")

    @property
    def aliases(self) -> Iterator[str]:
        for index in range(self.number_of_accounts):
            yield f"TEST::{index}"

    @property
    def accounts(self) -> Iterator["TestAccount"]:
        for index in range(self.number_of_accounts):
            yield cast(TestAccount, self.get_test_account(index))

    def get_test_account(self, index: int) -> TestAccountAPI:
        if index >= self.number_of_accounts:
            new_index = index - self.number_of_accounts
            return self.generated_accounts[new_index]

        try:
            return self.provider.get_test_account(index)
        except (NotImplementedError, ProviderNotConnectedError):
            return self.generate_account(index=index)

    def generate_account(self, index: Optional[int] = None) -> "TestAccountAPI":
        new_index = (
            self.number_of_accounts + len(self.generated_accounts) if index is None else index
        )
        generated_account = generate_dev_accounts(
            self.mnemonic, 1, hd_path=self.hd_path, start_index=new_index
        )[0]
        account = self.init_test_account(
            new_index, generated_account.address, generated_account.private_key
        )

        # Only cache if being created outside the expected number of accounts.
        # Else, ends up cached twice and caused logic problems elsewhere.
        if new_index >= self.number_of_accounts:
            self.generated_accounts.append(account)

        return account

    @classmethod
    def init_test_account(cls, index: int, address: AddressType, private_key: str) -> "TestAccount":
        return TestAccount(
            index=index,
            address_str=address,
            private_key=private_key,
        )

    def reset(self):
        self.generated_accounts = []


class TestAccount(ApeSigner, TestAccountAPI):
    index: int
    address_str: str

    __test__ = False

    @property
    def alias(self) -> str:
        return f"TEST::{self.index}"

    @cached_property
    def address(self) -> AddressType:
        # Overridden.
        return self.network_manager.ethereum.decode_address(self.address_str)

    @log_instead_of_fail(default="<TestAccount>")
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}_{self.index} {self.address}>"
