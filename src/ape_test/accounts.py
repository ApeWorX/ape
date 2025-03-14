import warnings
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, Optional, cast

from eip712.messages import EIP712Message
from eth_account import Account as EthAccount
from eth_account._utils.signing import sign_transaction_dict
from eth_account.messages import SignableMessage, encode_defunct
from eth_keys.datatypes import PrivateKey  # type: ignore
from eth_pydantic_types import HexBytes
from eth_utils import to_bytes, to_hex

from ape.api.accounts import TestAccountAPI, TestAccountContainerAPI
from ape.exceptions import ProviderNotConnectedError, SignatureError
from ape.types.signatures import MessageSignature, TransactionSignature
from ape.utils._web3_compat import sign_hash
from ape.utils.misc import log_instead_of_fail
from ape.utils.testing import generate_dev_accounts

if TYPE_CHECKING:
    from ape.api.transactions import TransactionAPI
    from ape.types.address import AddressType


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

    @TestAccountContainerAPI.mnemonic.setter
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
    def init_test_account(
        cls, index: int, address: "AddressType", private_key: str
    ) -> "TestAccount":
        return TestAccount(
            index=index,
            address_str=address,
            private_key=private_key,
        )

    def reset(self):
        self.generated_accounts = []


class TestAccount(TestAccountAPI):
    index: int
    address_str: str
    private_key: str

    __test__ = False

    @property
    def alias(self) -> str:
        return f"TEST::{self.index}"

    @property
    def address(self) -> "AddressType":
        return self.network_manager.ethereum.decode_address(self.address_str)

    @log_instead_of_fail(default="<TestAccount>")
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}_{self.index} {self.address_str}>"

    def sign_message(self, msg: Any, **signer_options) -> Optional[MessageSignature]:
        # Convert str and int to SignableMessage if needed
        if isinstance(msg, str):
            msg = encode_defunct(text=msg)
        elif isinstance(msg, int):
            msg = to_hex(msg)
            msg = encode_defunct(hexstr=msg)
        elif isinstance(msg, EIP712Message):
            # Convert EIP712Message to SignableMessage for handling below
            msg = msg.signable_message

        # Process SignableMessage
        if isinstance(msg, SignableMessage):
            signed_msg = EthAccount.sign_message(msg, self.private_key)
            return MessageSignature(
                v=signed_msg.v,
                r=to_bytes(signed_msg.r),
                s=to_bytes(signed_msg.s),
            )
        return None

    def sign_transaction(
        self, txn: "TransactionAPI", **signer_options
    ) -> Optional["TransactionAPI"]:
        # Signs any transaction that's given to it.
        # NOTE: Using JSON mode, as only primitive types can be signed.
        tx_data = txn.model_dump(mode="json", by_alias=True, exclude={"sender"})
        private_key = PrivateKey(HexBytes(self.private_key))

        # NOTE: var name `sig_r` instead of `r` to avoid clashing with pdb commands.
        try:
            (
                sig_v,
                sig_r,
                sig_s,
                _,
            ) = sign_transaction_dict(private_key, tx_data)
        except TypeError as err:
            # Occurs when missing properties on the txn that are needed to sign.
            raise SignatureError(str(err), transaction=txn) from err

        # NOTE: Using `to_bytes(hexstr=to_hex(sig_r))` instead of `to_bytes(sig_r)` as
        #   a performance optimization.
        txn.signature = TransactionSignature(
            v=sig_v,
            r=to_bytes(hexstr=to_hex(sig_r)),
            s=to_bytes(hexstr=to_hex(sig_s)),
        )

        return txn

    def sign_raw_msghash(self, msghash: HexBytes) -> MessageSignature:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            signed_msg = sign_hash(msghash, self.private_key)

        return MessageSignature(
            v=signed_msg.v,
            r=to_bytes(signed_msg.r),
            s=to_bytes(signed_msg.s),
        )
