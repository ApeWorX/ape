from collections.abc import Iterator
from functools import cached_property
from typing import TYPE_CHECKING, Any, Optional, Union, cast

from eth_pydantic_types import HexBytes
from eth_utils import to_hex

from ape.api.accounts import TestAccountAPI, TestAccountContainerAPI
from ape.api.address import BaseAddress
from ape.exceptions import ProviderNotConnectedError
from ape.types import AddressType
from ape.types.signatures import MessageSignature
from ape.utils.misc import ZERO_ADDRESS, log_instead_of_fail
from ape.utils.testing import generate_dev_accounts
from ape_accounts.accounts import ApeSigner
from ape_ethereum import Authorization
from ape_ethereum.transactions import TransactionType

if TYPE_CHECKING:
    from ape.api.transactions import TransactionAPI


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
            signer=ApeSigner(private_key=private_key),
        )

    def reset(self):
        self.generated_accounts = []


class TestAccount(TestAccountAPI):
    index: int
    address_str: str
    signer: ApeSigner

    __test__ = False

    @property
    def alias(self) -> str:
        return f"TEST::{self.index}"

    @cached_property
    def address(self) -> AddressType:
        return self.network_manager.ethereum.decode_address(self.address_str)

    @property
    def public_key(self) -> "HexBytes":
        return self.signer.public_key

    @property
    def private_key(self) -> str:
        return to_hex(self.signer.private_key)

    @log_instead_of_fail(default="<TestAccount>")
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}_{self.index} {self.address}>"

    def sign_authorization(
        self,
        address: AddressType,
        chain_id: Optional[int] = None,
        nonce: Optional[int] = None,
    ) -> Optional[MessageSignature]:
        if chain_id is None:
            chain_id = self.provider.chain_id

        return self.signer.sign_authorization(address, chain_id=chain_id, nonce=nonce)

    def sign_message(self, msg: Any, **signer_options) -> Optional[MessageSignature]:
        return self.signer.sign_message(msg, **signer_options)

    def sign_transaction(
        self, txn: "TransactionAPI", **signer_options
    ) -> Optional["TransactionAPI"]:
        return self.signer.sign_transaction(txn, **signer_options)

    def sign_raw_msghash(self, msghash: HexBytes) -> MessageSignature:
        return self.signer.sign_raw_msghash(msghash)

    def set_delegate(self, contract: Union[BaseAddress, AddressType, str], **txn_kwargs):
        contract_address = self.conversion_manager.convert(contract, AddressType)
        sig = self.sign_authorization(contract_address, nonce=self.nonce + 1)
        auth = Authorization.from_signature(
            address=contract_address,
            chain_id=self.provider.chain_id,
            # NOTE: `tx` uses `self.nonce`
            nonce=self.nonce + 1,
            signature=sig,
        )
        tx = self.provider.network.ecosystem.create_transaction(
            type=TransactionType.SET_CODE,
            authorizations=[auth],
            sender=self,
            # NOTE: Cannot target `ZERO_ADDRESS`
            receiver=txn_kwargs.pop("receiver", None) or self,
            **txn_kwargs,
        )
        return self.call(tx)

    def remove_delegate(self, **txn_kwargs):
        sig = self.sign_authorization(ZERO_ADDRESS, nonce=self.nonce + 1)
        auth = Authorization.from_signature(
            chain_id=self.provider.chain_id,
            address=ZERO_ADDRESS,
            # NOTE: `tx` uses `self.nonce`
            nonce=self.nonce + 1,
            signature=sig,
        )
        tx = self.provider.network.ecosystem.create_transaction(
            type=TransactionType.SET_CODE,
            authorizations=[auth],
            sender=self,
            # NOTE: Cannot target `ZERO_ADDRESS`
            receiver=txn_kwargs.pop("receiver", None) or self,
            **txn_kwargs,
        )
        return self.call(tx)
