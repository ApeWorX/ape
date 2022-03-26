from typing import Iterator, List, Optional

from eth_account import Account as EthAccount  # type: ignore
from eth_account.messages import SignableMessage
from eth_utils import to_bytes

from ape.api import TestAccountAPI, TestAccountContainerAPI, TransactionAPI
from ape.types import AddressType, MessageSignature, TransactionSignature
from ape.utils import GeneratedDevAccount, cached_property, generate_dev_accounts, to_address


class TestAccountContainer(TestAccountContainerAPI):
    @property
    def config(self):
        return self.config_manager.get_config("test")

    @cached_property
    def _dev_accounts(self) -> List[GeneratedDevAccount]:
        mnemonic = self.config["mnemonic"]
        return generate_dev_accounts(mnemonic)

    @property
    def aliases(self) -> Iterator[str]:
        for index in range(len(self)):
            yield f"dev_{index}"

    @property
    def accounts(self) -> Iterator["TestAccount"]:
        for index in range(len(self)):
            account = self._dev_accounts[index]
            yield TestAccount(
                index=index,
                address_str=account.address,
                private_key=account.private_key,
            )

    def __len__(self) -> int:
        return len(self._dev_accounts)


class TestAccount(TestAccountAPI):
    index: int
    address_str: str
    private_key: str

    @property
    def alias(self) -> str:
        return f"dev_{self.index}"

    @property
    def address(self) -> AddressType:
        return to_address(self.address_str)

    def sign_message(self, msg: SignableMessage) -> Optional[MessageSignature]:
        signed_msg = EthAccount.sign_message(msg, self.private_key)
        return MessageSignature(  # type: ignore
            v=signed_msg.v,
            r=to_bytes(signed_msg.r),
            s=to_bytes(signed_msg.s),
        )

    def sign_transaction(self, txn: TransactionAPI) -> Optional[TransactionSignature]:
        signed_txn = EthAccount.sign_transaction(txn.dict(), self.private_key)
        return TransactionSignature(  # type: ignore
            v=signed_txn.v,
            r=to_bytes(signed_txn.r),
            s=to_bytes(signed_txn.s),
        )
