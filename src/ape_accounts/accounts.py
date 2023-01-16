import json
from pathlib import Path
from typing import Iterator, Optional

import click
from eth_account import Account as EthAccount
from eth_utils import to_bytes
from hexbytes import HexBytes

from ape.api import AccountAPI, AccountContainerAPI, TransactionAPI
from ape.exceptions import AccountsError
from ape.logging import logger
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

    @property
    def accounts(self) -> Iterator[AccountAPI]:
        for keyfile in self._keyfiles:
            yield KeyfileAccount(keyfile_path=keyfile)

    def __len__(self) -> int:
        return len([*self._keyfiles])


# NOTE: `AccountAPI` is an BaseInterfaceModel
class KeyfileAccount(AccountAPI):

    keyfile_path: Path
    locked: bool = True
    __autosign: bool = False
    __cached_key: Optional[HexBytes] = None

    def __repr__(self):
        return f"<{self.__class__.__name__} address={self.address} alias={self.alias}>"

    @property
    def alias(self) -> str:
        return self.keyfile_path.stem

    @property
    def keyfile(self) -> dict:
        return json.loads(self.keyfile_path.read_text())

    @property
    def address(self) -> AddressType:
        return self.network_manager.ethereum.decode_address(self.keyfile["address"])

    @property
    def __key(self) -> HexBytes:
        if self.__cached_key is not None:
            if not self.locked:
                click.echo(f"Using cached key for '{self.alias}'")
                return self.__cached_key
            else:
                self.__cached_key = None

        passphrase = self._prompt_for_passphrase(default="")
        key = self.__decrypt_keyfile(passphrase)

        if click.confirm(f"Leave '{self.alias}' unlocked?"):
            self.locked = False
            self.__cached_key = key

        return key

    def unlock(self, passphrase: Optional[str] = None):
        passphrase = passphrase or self._prompt_for_passphrase(
            f"Enter passphrase to permanently unlock '{self.alias}'"
        )
        self.__cached_key = self.__decrypt_keyfile(passphrase)
        self.locked = False

    def lock(self):
        self.locked = True

    def change_password(self):
        self.locked = True  # force entering passphrase to get key
        key = self.__key

        passphrase = self._prompt_for_passphrase("Create new passphrase", confirmation_prompt=True)
        self.keyfile_path.write_text(json.dumps(EthAccount.encrypt(key, passphrase)))

    def delete(self):
        passphrase = self._prompt_for_passphrase(
            f"Enter passphrase to delete '{self.alias}'", default=""
        )
        self.__decrypt_keyfile(passphrase)
        self.keyfile_path.unlink()

    def sign_message(self, msg: SignableMessage) -> Optional[MessageSignature]:
        user_approves = self.__autosign or click.confirm(f"{msg}\n\nSign: ")
        if not user_approves:
            return None

        signed_msg = EthAccount.sign_message(msg, self.__key)
        return MessageSignature(
            v=signed_msg.v,
            r=to_bytes(signed_msg.r),
            s=to_bytes(signed_msg.s),
        )

    def sign_transaction(self, txn: TransactionAPI, **kwargs) -> Optional[TransactionAPI]:
        user_approves = self.__autosign or click.confirm(f"{txn}\n\nSign: ")
        if not user_approves:
            return None

        signature = EthAccount.sign_transaction(
            txn.dict(exclude_none=True, by_alias=True), self.__key
        )
        txn.signature = TransactionSignature(
            v=signature.v,
            r=to_bytes(signature.r),
            s=to_bytes(signature.s),
        )

        return txn

    def set_autosign(self, enabled: bool, passphrase: Optional[str] = None):
        """
        Allow this account to automatically sign messages and transactions.

        Args:
            enabled (bool): ``True`` to enable, ``False`` to disable.
            passphrase (Optional[str]): Optionally provide the passphrase.
              If not provided, you will be prompted to enter it.
        """
        if enabled:
            self.unlock(passphrase=passphrase)
            logger.warning("Danger! This account will now sign any transaction it's given.")

        self.__autosign = enabled
        if not enabled:
            # Re-lock if was turning off
            self.locked = True
            self.__cached_key = None

    def _prompt_for_passphrase(self, message: Optional[str] = None, **kwargs):
        message = message or f"Enter passphrase to unlock '{self.alias}'"
        return click.prompt(
            message,
            hide_input=True,
            **kwargs,
        )

    def __decrypt_keyfile(self, passphrase: str) -> HexBytes:
        try:
            return EthAccount.decrypt(self.keyfile, passphrase)
        except ValueError as err:
            raise InvalidPasswordError() from err
