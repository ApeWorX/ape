import json
import warnings
from collections.abc import Iterator
from os import environ
from pathlib import Path
from typing import Any, Optional

import click
from eip712.messages import EIP712Message
from eth_account import Account as EthAccount
from eth_account.hdaccount import ETHEREUM_DEFAULT_PATH
from eth_account.messages import encode_defunct
from eth_account.signers.local import LocalAccount
from eth_keys import keys  # type: ignore
from eth_pydantic_types import HexBytes
from eth_utils import to_bytes, to_hex

from ape.api.accounts import AccountAPI, AccountContainerAPI
from ape.api.transactions import TransactionAPI
from ape.exceptions import AccountsError
from ape.logging import logger
from ape.types.address import AddressType
from ape.types.signatures import MessageSignature, SignableMessage, TransactionSignature
from ape.utils.basemodel import ManagerAccessMixin
from ape.utils.misc import log_instead_of_fail
from ape.utils.validators import _validate_account_alias, _validate_account_passphrase


class InvalidPasswordError(AccountsError):
    """
    Raised when password to unlock an account is incorrect.
    """

    def __init__(self):
        super().__init__("Invalid password")


class AccountContainer(AccountContainerAPI):
    loaded_accounts: dict[str, "KeyfileAccount"] = {}

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
    __cached_key: Optional[bytes] = None

    @log_instead_of_fail(default="<KeyfileAccount>")
    def __repr__(self) -> str:
        # NOTE: Prevent errors from preventing repr from working.
        address_str = f" address={self.address} " if self.address else ""
        alias_str = f" alias={self.alias} " if self.alias else ""
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
    def __key(self) -> bytes:
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

        self.keyfile_path.write_text(json.dumps(key_file_data), encoding="utf8")

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
        self.keyfile_path.write_text(
            json.dumps(EthAccount.encrypt(key, passphrase)), encoding="utf8"
        )

    def delete(self):
        passphrase = self._prompt_for_passphrase(
            f"Enter passphrase to delete '{self.alias}'", default=""
        )
        self.__decrypt_keyfile(passphrase)
        self.keyfile_path.unlink()

    def sign_message(self, msg: Any, **signer_options) -> Optional[MessageSignature]:
        if isinstance(msg, str):
            display_msg = f"Signing raw string: '{msg}'"
            msg = encode_defunct(text=msg)

        elif isinstance(msg, int):
            display_msg = f"Signing raw integer: {msg}"
            msg = encode_defunct(hexstr=to_hex(msg))

        elif isinstance(msg, bytes):
            display_msg = f"Signing raw bytes: '{to_hex(msg)}'"
            msg = encode_defunct(primitive=msg)

        elif isinstance(msg, EIP712Message):
            # Display message data to user
            display_msg = "Signing EIP712 Message\n"

            # Domain Data
            display_msg += "Domain\n"
            if msg._name_:
                display_msg += f"\tName: {msg._name_}\n"
            if msg._version_:
                display_msg += f"\tVersion: {msg._version_}\n"
            if msg._chainId_:
                display_msg += f"\tChain ID: {msg._chainId_}\n"
            if msg._verifyingContract_:
                display_msg += f"\tContract: {msg._verifyingContract_}\n"
            if msg._salt_:
                display_msg += f"\tSalt: {to_hex(msg._salt_)}\n"

            # Message Data
            display_msg += "Message\n"
            for field, value in msg._body_["message"].items():
                if isinstance(value, bytes):
                    value = to_hex(value)
                display_msg += f"\t{field}: {value}\n"

            # Convert EIP712Message to SignableMessage for handling below
            msg = msg.signable_message

        elif isinstance(msg, SignableMessage):
            display_msg = str(msg)

        else:
            logger.warning("Unsupported message type, (type=%r, msg=%r)", type(msg), msg)
            return None

        if self.__autosign or click.confirm(f"{display_msg}\n\nSign: "):
            signed_msg = EthAccount.sign_message(msg, self.__key)

        else:
            return None

        return MessageSignature(
            v=signed_msg.v,
            r=to_bytes(signed_msg.r),
            s=to_bytes(signed_msg.s),
        )

    def sign_transaction(self, txn: TransactionAPI, **signer_options) -> Optional[TransactionAPI]:
        user_approves = self.__autosign or click.confirm(f"{txn}\n\nSign: ")
        if not user_approves:
            return None

        signature = EthAccount.sign_transaction(
            txn.model_dump(exclude_none=True, by_alias=True), self.__key
        )
        txn.signature = TransactionSignature(
            v=signature.v,
            r=to_bytes(signature.r),
            s=to_bytes(signature.s),
        )

        return txn

    def sign_raw_msghash(self, msghash: HexBytes) -> Optional[MessageSignature]:
        logger.warning(
            "Signing a raw hash directly is a dangerous action which could risk "
            "substantial losses! Only confirm if you are 100% sure of the origin!"
        )

        # NOTE: Signing a raw hash is so dangerous, we don't want to allow autosigning it
        if not click.confirm("Please confirm you wish to sign using `EthAccount.signHash`"):
            return None

        # Ignoring misleading deprecated warning from web3.py.
        # Also, we have already warned the user about the safety.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            signed_msg = EthAccount.signHash(msghash, self.__key)

        return MessageSignature(
            v=signed_msg.v,
            r=to_bytes(signed_msg.r),
            s=to_bytes(signed_msg.s),
        )

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

    def __decrypt_keyfile(self, passphrase: str) -> bytes:
        try:
            return EthAccount.decrypt(self.keyfile, passphrase)
        except ValueError as err:
            raise InvalidPasswordError() from err


def _write_and_return_account(alias: str, passphrase: str, account: LocalAccount) -> KeyfileAccount:
    """Write an account to disk and return an Ape KeyfileAccount"""
    path = ManagerAccessMixin.account_manager.containers["accounts"].data_folder.joinpath(
        f"{alias}.json"
    )
    path.write_text(json.dumps(EthAccount.encrypt(account.key, passphrase)), encoding="utf8")

    return KeyfileAccount(keyfile_path=path)


def generate_account(
    alias: str, passphrase: str, hd_path: str = ETHEREUM_DEFAULT_PATH, word_count: int = 12
) -> tuple[KeyfileAccount, str]:
    """
    Generate a new account.

    Args:
        alias (str): The alias name of the account.
        passphrase (str): Passphrase used to encrypt the account storage file.
        hd_path (str): The hierarchal deterministic path to use when generating the account.
            Defaults to `m/44'/60'/0'/0/0`.
        word_count (int): The amount of words to use in the generated mnemonic.

    Returns:
        Tuple of :class:`~ape_accounts.accounts.KeyfileAccount` and mnemonic for the generated
        account.
    """
    EthAccount.enable_unaudited_hdwallet_features()

    alias = _validate_account_alias(alias)
    passphrase = _validate_account_passphrase(passphrase)

    account, mnemonic = EthAccount.create_with_mnemonic(num_words=word_count, account_path=hd_path)
    ape_account = _write_and_return_account(alias, passphrase, account)
    return ape_account, mnemonic


def import_account_from_mnemonic(
    alias: str, passphrase: str, mnemonic: str, hd_path: str = ETHEREUM_DEFAULT_PATH
) -> KeyfileAccount:
    """
    Import a new account from a mnemonic seed phrase.

    Args:
        alias (str): The alias name of the account.
        passphrase (str): Passphrase used to encrypt the account storage file.
        mnemonic (str): List of space-separated words representing the mnemonic seed phrase.
        hd_path (str): The hierarchal deterministic path to use when generating the account.
            Defaults to `m/44'/60'/0'/0/0`.

    Returns:
        Tuple of AccountAPI and mnemonic for the generated account.
    """
    EthAccount.enable_unaudited_hdwallet_features()

    alias = _validate_account_alias(alias)
    passphrase = _validate_account_passphrase(passphrase)

    account = EthAccount.from_mnemonic(mnemonic, account_path=hd_path)

    return _write_and_return_account(alias, passphrase, account)


def import_account_from_private_key(
    alias: str, passphrase: str, private_key: str
) -> KeyfileAccount:
    """
    Import a new account from a mnemonic seed phrase.

    Args:
        alias (str): The alias name of the account.
        passphrase (str): Passphrase used to encrypt the account storage file.
        private_key (str): Hex string private key to import.

    Returns:
        Tuple of AccountAPI and mnemonic for the generated account.
    """
    alias = _validate_account_alias(alias)
    passphrase = _validate_account_passphrase(passphrase)

    account = EthAccount.from_key(to_bytes(hexstr=private_key))

    return _write_and_return_account(alias, passphrase, account)
