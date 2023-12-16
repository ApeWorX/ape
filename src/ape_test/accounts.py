from typing import Any, Iterator, List, Optional

from eth_account import Account as EthAccount
from eth_account.messages import SignableMessage, encode_defunct
from eth_utils import to_bytes
from hexbytes import HexBytes

from ape.api import TestAccountAPI, TestAccountContainerAPI, TransactionAPI
from ape.types import AddressType, MessageSignature, TransactionSignature
from ape.utils import GeneratedDevAccount, generate_dev_accounts


class TestAccountContainer(TestAccountContainerAPI):
    num_generated: int = 0
    mnemonic: str = ""
    num_of_accounts: int = 0
    hd_path: str = ""
    _accounts: List["TestAccount"] = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.init()

    def init(self):
        self.mnemonic = self.config["mnemonic"]
        self.num_of_accounts = self.config["number_of_accounts"]
        self.hd_path = self.config["hd_path"]
        self._accounts = []

        for index, account in enumerate(self._dev_accounts):
            self._accounts.append(
                TestAccount(
                    index=index, address_str=account.address, private_key=account.private_key
                )
            )

    def __len__(self) -> int:
        return self.num_of_accounts

    @property
    def config(self):
        return self.config_manager.get_config("test")

    @property
    def _dev_accounts(self) -> List[GeneratedDevAccount]:
        return generate_dev_accounts(
            self.mnemonic,
            number_of_accounts=self.num_of_accounts,
            hd_path=self.hd_path,
        )

    @property
    def aliases(self) -> Iterator[str]:
        for index in range(self.num_of_accounts):
            yield f"TEST::{index}"

    @property
    def _is_config_changed(self):
        current_mnemonic = self.config["mnemonic"]
        current_number = self.config["number_of_accounts"]
        current_hd_path = self.config["hd_path"]
        return (
            self.mnemonic != current_mnemonic
            or self.num_of_accounts != current_number
            or self.hd_path != current_hd_path
        )

    @property
    def accounts(self) -> Iterator["TestAccount"]:
        # As TestAccountManager only uses accounts property this works!
        if self._is_config_changed:
            self.init()
        for account in self._accounts:
            yield account

    def generate_account(self) -> "TestAccountAPI":
        new_index = self.num_of_accounts + self.num_generated
        self.num_generated += 1
        generated_account = generate_dev_accounts(
            self.mnemonic, 1, hd_path=self.hd_path, start_index=new_index
        )[0]
        acc = TestAccount(
            index=new_index,
            address_str=generated_account.address,
            private_key=generated_account.private_key,
        )
        return acc


class TestAccount(TestAccountAPI):
    index: int
    address_str: str
    private_key: str

    __test__ = False

    @property
    def alias(self) -> str:
        return f"TEST::{self.index}"

    @property
    def address(self) -> AddressType:
        return self.network_manager.ethereum.decode_address(self.address_str)

    def sign_message(self, msg: Any, **signer_options) -> Optional[MessageSignature]:
        # Convert str and int to SignableMessage if needed
        if isinstance(msg, str):
            msg = encode_defunct(text=msg)
        elif isinstance(msg, int):
            msg = HexBytes(msg).hex()
            msg = encode_defunct(hexstr=msg)

        # Process SignableMessage
        if isinstance(msg, SignableMessage):
            signed_msg = EthAccount.sign_message(msg, self.private_key)
            return MessageSignature(
                v=signed_msg.v,
                r=to_bytes(signed_msg.r),
                s=to_bytes(signed_msg.s),
            )
        return None

    def sign_transaction(self, txn: TransactionAPI, **signer_options) -> Optional[TransactionAPI]:
        # Signs anything that's given to it
        signature = EthAccount.sign_transaction(txn.model_dump(mode="json"), self.private_key)
        txn.signature = TransactionSignature(
            v=signature.v,
            r=to_bytes(signature.r),
            s=to_bytes(signature.s),
        )

        return txn
