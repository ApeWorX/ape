from typing import Iterator, List, Optional

from eth_account import Account as EthAccount
from eth_account.messages import SignableMessage
from eth_utils import to_bytes

from ape.api import TestAccountAPI, TestAccountContainerAPI, TransactionAPI
from ape.types import AddressType, MessageSignature, TransactionSignature
from ape.utils import GeneratedDevAccount, generate_dev_accounts


class TestAccountContainer(TestAccountContainerAPI):
    _num_generated = 0

    @property
    def config(self):
        return self.config_manager.get_config("test")

    @property
    def _dev_accounts(self) -> List[GeneratedDevAccount]:
        mnemonic = self.config["mnemonic"]
        return generate_dev_accounts(mnemonic, number_of_accounts=self.config["number_of_accounts"])

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

    def generate_account(self) -> "TestAccountAPI":
        new_index = len(self) + self._num_generated
        self._num_generated += 1
        generated_account = generate_dev_accounts(
            self.config["mnemonic"], 1, start_index=new_index
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

    @property
    def alias(self) -> str:
        return f"dev_{self.index}"

    @property
    def address(self) -> AddressType:
        return self.network_manager.ethereum.decode_address(self.address_str)

    def sign_message(self, msg: SignableMessage) -> Optional[MessageSignature]:
        signed_msg = EthAccount.sign_message(msg, self.private_key)
        return MessageSignature(
            v=signed_msg.v,
            r=to_bytes(signed_msg.r),
            s=to_bytes(signed_msg.s),
        )

    def sign_transaction(self, txn: TransactionAPI, **kwargs) -> Optional[TransactionAPI]:
        # Signs anything that's given to it
        signature = EthAccount.sign_transaction(txn.dict(), self.private_key)
        txn.signature = TransactionSignature(
            v=signature.v,
            r=to_bytes(signature.r),
            s=to_bytes(signature.s),
        )

        return txn
