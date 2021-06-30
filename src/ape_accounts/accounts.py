import json
from pathlib import Path
from typing import Iterator, Optional

import click
from eth_account import Account as EthAccount  # type: ignore
from eth_account.datastructures import SignedMessage  # type: ignore
from eth_account.messages import SignableMessage  # type: ignore

from ape.api import AccountAPI, AccountContainerAPI, TransactionAPI
from ape.convert import to_address


class AccountContainer(AccountContainerAPI):
    @property
    def _keyfiles(self) -> Iterator[Path]:
        return self.data_folder.glob("*.json")

    @property
    def aliases(self) -> Iterator[str]:
        for p in self._keyfiles:
            yield p.stem

    def __len__(self) -> int:
        return len([*self._keyfiles])

    def __iter__(self) -> Iterator[AccountAPI]:
        for keyfile in self._keyfiles:
            yield KeyfileAccount(self, keyfile)  # type: ignore


# NOTE: `AccountAPI` is a dataclass
class KeyfileAccount(AccountAPI):
    _keyfile: Path

    def __post_init__(self):
        self.locked = True
        self.__cached_key = None

    @property
    def alias(self) -> str:
        return self._keyfile.stem

    @property
    def keyfile(self) -> dict:
        return json.loads(self._keyfile.read_text())

    @property
    def address(self) -> str:
        return to_address(self.keyfile["address"])

    @property
    def __key(self) -> EthAccount:
        if self.__cached_key is not None:
            if not self.locked:
                click.echo(f"Using cached key for '{self.alias}'")
                return self.__cached_key
            else:
                self.__cached_key = None

        passphrase = click.prompt(
            f"Enter Passphrase to unlock '{self.alias}'",
            hide_input=True,
            default="",  # Just in case there's no passphrase
        )

        try:
            key = EthAccount.decrypt(self.keyfile, passphrase)

        except ValueError as e:
            raise Exception("Invalid password") from e

        if click.confirm(f"Leave '{self.alias}' unlocked?"):
            self.locked = False
            self.__cached_key = key

        return key

    def unlock(self):
        passphrase = click.prompt(
            f"Enter Passphrase to permanently unlock '{self.alias}'",
            hide_input=True,
        )

        try:
            self.__cached_key = EthAccount.decrypt(self.keyfile, passphrase)

        except ValueError as e:
            raise Exception("Invalid password") from e

    def lock(self):
        self.locked = True

    def change_password(self):
        self.locked = True  # force entering passphrase to get key
        key = self.__key

        passphrase = click.prompt(
            "Create New Passphrase",
            hide_input=True,
            confirmation_prompt=True,
        )

        self._keyfile.write_text(json.dumps(EthAccount.encrypt(key, passphrase)))

    def delete(self):
        passphrase = click.prompt(
            f"Enter Passphrase to delete '{self.alias}'",
            hide_input=True,
            default="",  # Just in case there's no passphrase
        )

        EthAccount.decrypt(self.keyfile, passphrase)

        self._keyfile.unlink()

    def sign_message(self, msg: SignableMessage) -> Optional[SignedMessage]:
        if self.locked and not click.confirm(f"{msg}\n\nSign: "):
            return None

        return EthAccount.sign_message(msg, self.__key)

    def sign_transaction(self, txn: TransactionAPI) -> Optional[TransactionAPI]:
        if self.locked and not click.confirm(f"{txn}\n\nSign: "):
            return None

        signed_txn = EthAccount.sign_transaction(txn.as_dict(), self.__key)

        txn.signature = (
            signed_txn.v.to_bytes(1, "big")
            + signed_txn.r.to_bytes(32, "big")
            + signed_txn.s.to_bytes(32, "big")
        )

        return txn
