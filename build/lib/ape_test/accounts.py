from typing import Iterator, List, Optional

from eth_account import Account as EthAccount  # type: ignore
from eth_account.messages import SignableMessage
from eth_utils import to_bytes

from ape.api import TestAccountAPI, TestAccountContainerAPI, TransactionAPI
from ape.convert import to_address
from ape.types import AddressType, MessageSignature, TransactionSignature
from ape.utils import GeneratedDevAccount, cached_property, generate_dev_accounts


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
        for index in range(0, len(self)):
            yield f"dev_{index}"

    def __len__(self) -> int:
        return len(self._dev_accounts)

    def __iter__(self) -> Iterator[TestAccountAPI]:
        for index in range(0, len(self)):
            account = self._dev_accounts[index]
            yield TestAccount(
                self, _index=index, _address=account.address, _private_key=account.private_key
            )  # type: ignore


class TestAccount(TestAccountAPI):
    _index: int
    _address: str
    _private_key: str

    @property
    def alias(self) -> str:
        return f"dev_{self._index}"

    @property
    def address(self) -> AddressType:
        return to_address(self._address)

    def sign_message(self, msg: SignableMessage) -> Optional[MessageSignature]:
        signed_msg = EthAccount.sign_message(msg, self._private_key)
        return MessageSignature(  # type: ignore
            v=signed_msg.v,
            r=to_bytes(signed_msg.r),
            s=to_bytes(signed_msg.s),
        )

    def sign_transaction(self, txn: TransactionAPI) -> Optional[TransactionSignature]:
        signed_txn = EthAccount.sign_transaction(txn.as_dict(), self._private_key)
        return TransactionSignature(  # type: ignore
            v=signed_txn.v,
            r=to_bytes(signed_txn.r),
            s=to_bytes(signed_txn.s),
        )
