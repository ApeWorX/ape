import json
from pathlib import Path
from typing import Iterator, Optional

import click
from eth_account import Account  # type: ignore
from eth_account.datastructures import SignedMessage, SignedTransaction  # type: ignore
from eth_account.messages import SignableMessage  # type: ignore
from eth_utils import to_bytes

from ape.api.accounts import AccountAPI, AccountContainerAPI
from ape.convert import to_address


class AccountContainer(AccountContainerAPI):
    def __init__(self):
        # Inject container into account class
        KeyfileAccount.container = self

    @property
    def _keyfiles(self) -> Iterator[Path]:
        return self.DATA_FOLDER.glob("*.json")

    @property
    def aliases(self) -> Iterator[str]:
        for p in self._keyfiles:
            yield p.stem

    def __len__(self) -> int:
        return len([*self._keyfiles])

    def __iter__(self) -> Iterator[AccountAPI]:
        for keyfile in self._keyfiles:
            yield KeyfileAccount(keyfile)


class KeyfileAccount(AccountAPI):
    def __init__(self, keyfile: Path):
        self._keyfile = keyfile
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

    @classmethod
    def generate(cls, alias: str) -> "KeyfileAccount":
        path = cls.container.DATA_FOLDER.joinpath(f"{alias}.json")
        extra_entropy = click.prompt(
            "Add extra entropy for key generation...",
            hide_input=True,
        )
        a = Account.create(extra_entropy)
        passphrase = click.prompt(
            "Create Passphrase",
            hide_input=True,
            confirmation_prompt=True,
        )
        path.write_text(json.dumps(Account.encrypt(a.key, passphrase)))
        return cls(path)

    @classmethod
    def from_key(cls, alias: str) -> "KeyfileAccount":
        path = cls.container.DATA_FOLDER.joinpath(f"{alias}.json")
        key = click.prompt("Enter Private Key", hide_input=True)
        a = Account.from_key(to_bytes(hexstr=key))
        passphrase = click.prompt(
            "Create Passphrase",
            hide_input=True,
            confirmation_prompt=True,
        )
        path.write_text(json.dumps(Account.encrypt(a.key, passphrase)))
        return cls(path)

    @property
    def __key(self) -> Account:
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

        key = Account.decrypt(self.keyfile, passphrase)

        if click.confirm("Leave '{self.alias}' unlocked?"):
            self.locked = False
            self.__cached_key = key

        return key

    def unlock(self):
        passphrase = click.prompt(
            f"Enter Passphrase to permanently unlock '{self.alias}'",
            hide_input=True,
        )

        self.__cached_key = Account.decrypt(self.keyfile, passphrase)

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

        self._keyfile.write_text(json.dumps(Account.encrypt(key, passphrase)))

    def delete(self):
        passphrase = click.prompt(
            f"Enter Passphrase to delete '{self.alias}'",
            hide_input=True,
            default="",  # Just in case there's no passphrase
        )

        Account.decrypt(self.keyfile, passphrase)

        self._keyfile.unlink()

    def sign_message(self, msg: SignableMessage) -> Optional[SignedMessage]:
        if self.locked and not click.confirm(f"Sign: {msg}"):
            return None

        return Account.sign_message(msg, self.__key)

    def sign_transaction(self, txn: dict) -> Optional[SignedTransaction]:
        if self.locked and not click.confirm(f"Sign: {txn}"):
            return None

        return Account.sign_transaction(txn, self.__key)


# TODO: LedgerAccount, TrezorAccount, etc. for hw wallets
