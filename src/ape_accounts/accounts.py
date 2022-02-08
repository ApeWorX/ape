import json
from pathlib import Path
from typing import Iterator, Optional

import click
from eth_account import Account as EthAccount  # type: ignore
from eth_utils import to_bytes

from ape.api import AccountAPI, AccountContainerAPI, TransactionAPI
from ape.convert import to_address
from ape.exceptions import AccountsError
from ape.types import AddressType, MessageSignature, SignableMessage, TransactionSignature


class InvalidPasswordError(AccountsError):
    """
    Raised when password to unlock an account is incorrect.
    """

    def __init__(self):
        super().__init__("Invalid password")


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

    def __repr__(self):
        return f"<{self.__class__.__name__} address={self.address} alias={self.alias}>"

    @property
    def alias(self) -> str:
        return self._keyfile.stem

    @property
    def keyfile(self) -> dict:
        return json.loads(self._keyfile.read_text())

    @property
    def address(self) -> AddressType:
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

        key = self.__decrypt_keyfile(passphrase)

        if click.confirm(f"Leave '{self.alias}' unlocked?"):
            self.locked = False
            self.__cached_key = key

        return key

    def unlock(self):
        passphrase = click.prompt(
            f"Enter Passphrase to permanently unlock '{self.alias}'",
            hide_input=True,
        )
        self.__cached_key = self.__decrypt_keyfile(passphrase)
        self.locked = False

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
        self.__decrypt_keyfile(passphrase)
        self._keyfile.unlink()

    def sign_message(self, msg: SignableMessage) -> Optional[MessageSignature]:
        if self.locked and not click.confirm(f"{msg}\n\nSign: "):
            return None

        signed_msg = EthAccount.sign_message(msg, self.__key)
        return MessageSignature(  # type: ignore
            v=signed_msg.v,
            r=to_bytes(signed_msg.r),
            s=to_bytes(signed_msg.s),
        )

    def sign_transaction(self, txn: TransactionAPI) -> Optional[TransactionSignature]:
        if self.locked and not click.confirm(f"{txn}\n\nSign: "):
            return None

        signed_txn = EthAccount.sign_transaction(txn.as_dict(), self.__key)
        return TransactionSignature(  # type: ignore
            v=signed_txn.v,
            r=to_bytes(signed_txn.r),
            s=to_bytes(signed_txn.s),
        )

    def __decrypt_keyfile(self, passphrase: str) -> EthAccount:
        try:
            return EthAccount.decrypt(self.keyfile, passphrase)
        except ValueError as err:
            raise InvalidPasswordError() from err
