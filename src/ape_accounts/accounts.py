import json
from os import environ
from pathlib import Path
from typing import Dict, Iterator, Optional

import click
from eth_account import Account as EthAccount
from eth_keys import keys  # type: ignore
from eth_utils import to_bytes
from ethpm_types import HexBytes

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
    loaded_accounts: Dict[str, "KeyfileAccount"] = {}

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
            if keyfile.stem not in self.loaded_accounts:
                keyfile_account = KeyfileAccount(keyfile_path=keyfile)
                self.loaded_accounts[keyfile.stem] = keyfile_account

            yield self.loaded_accounts[keyfile.stem]

    def __len__(self) -> int:
        return len([*self._keyfiles])


# NOTE: `AccountAPI` is an BaseInterfaceModel
class KeyfileAccount(AccountAPI):
    keyfile_path: Path
    locked: bool = True
    __autosign: bool = False
    __cached_key: Optional[HexBytes] = None

    def __repr__(self):
        # NOTE: Prevent errors from preventing repr from working.
        try:
            address_str = f" address={self.address} "
        except Exception:
            address_str = ""

        try:
            alias_str = f" alias={self.alias} "
        except Exception:
            alias_str = ""

        return f"<{self.__class__.__name__}{address_str}{alias_str}>"

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
                logger.warning("Using cached key for %s", self.alias)
                return self.__cached_key
            self.__cached_key = None

        passphrase = self._prompt_for_passphrase(default="")
        key = self.__decrypt_keyfile(passphrase)

        if click.confirm(f"Leave '{self.alias}' unlocked?"):
            self.locked = False
            self.__cached_key = key

        return key

    @property
    def public_key(self) -> HexBytes:
        if "public_key" in self.keyfile:
            return HexBytes(bytes.fromhex(self.keyfile["public_key"]))
        key = self.__key

        # Derive the public key from the private key
        pk = keys.PrivateKey(key)
        # convert from eth_keys.datatypes.PublicKey to str to make it HexBytes
        publicKey = str(pk.public_key)

        key_file_data = self.keyfile
        key_file_data["public_key"] = publicKey[2:]

        self.keyfile_path.write_text(json.dumps(key_file_data))

        return HexBytes(bytes.fromhex(publicKey[2:]))

    def unlock(self, passphrase: Optional[str] = None):
        if not passphrase:
            # Check if environment variable is available
            env_variable = f"APE_ACCOUNTS_{self.alias}_PASSPHRASE"
            passphrase = environ.get(env_variable, None)

            if passphrase:
                # Passphrase found in environment variable
                logger.info(
                    f"Using passphrase for account '{self.alias}' from environment variable"
                )
            else:
                # Passphrase not found, prompt for it
                passphrase = self._prompt_for_passphrase(
                    f"Enter passphrase to permanently unlock '{self.alias}'"
                )
        assert passphrase is not None, "Passphrase can't be 'None'"
        # Rest of the code to unlock the account using the passphrase
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

    def _prompt_for_passphrase(self, message: Optional[str] = None, **kwargs) -> str:
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
