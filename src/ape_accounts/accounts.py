import json
import warnings
from collections.abc import Iterator
from functools import cached_property
from os import environ
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, cast

import click
from eip712.messages import EIP712Message
from eth_account import Account as EthAccount
from eth_account._utils.signing import sign_transaction_dict
from eth_account.hdaccount import ETHEREUM_DEFAULT_PATH
from eth_account.messages import encode_defunct
from eth_keys.datatypes import PrivateKey
from eth_pydantic_types import HexBytes
from eth_pydantic_types import HexStr as PydanticHexStr
from eth_typing import HexStr
from eth_utils import remove_0x_prefix, to_bytes, to_canonical_address, to_hex

from ape.api.accounts import AccountAPI, AccountContainerAPI
from ape.api.address import BaseAddress
from ape.exceptions import AccountsError, SignatureError
from ape.logging import logger
from ape.types.address import AddressType
from ape.types.signatures import MessageSignature, SignableMessage, TransactionSignature
from ape.utils.basemodel import ManagerAccessMixin
from ape.utils.misc import ZERO_ADDRESS, derive_public_key, log_instead_of_fail
from ape.utils.validators import _validate_account_alias, _validate_account_passphrase
from ape_ethereum import Authorization
from ape_ethereum.transactions import TransactionType

if TYPE_CHECKING:
    from eth_account.signers.local import LocalAccount
    from typing_extensions import Self

    from ape.api.transactions import TransactionAPI


class InvalidPasswordError(AccountsError):
    """
    Raised when password to unlock an account is incorrect.
    """

    def __init__(self):
        super().__init__("Invalid password")


class AccountContainer(AccountContainerAPI):
    """
    A folder of encrypted keyfiles, each loaded as this container's ``account_type``.
    """

    loaded_accounts: ClassVar[dict[str, "BaseKeyfileAccount"]] = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.loaded_accounts = {}

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
                keyfile_account = self.keyfile_account_type(keyfile_path=keyfile)
                self.loaded_accounts[keyfile.stem] = keyfile_account

            yield self.loaded_accounts[keyfile.stem]

    def __len__(self) -> int:
        return len([*self._keyfiles])

    @property
    def keyfile_account_type(self) -> type["BaseKeyfileAccount"]:
        return cast(type[BaseKeyfileAccount], self.account_type)

    def create_account(self, alias: str, passphrase: str, secret: bytes) -> "BaseKeyfileAccount":
        """
        Encrypt ``secret`` into a new keyfile named ``alias`` and return its account.
        """
        alias = _validate_account_alias(alias)
        passphrase = _validate_account_passphrase(passphrase)
        path = self.data_folder.joinpath(f"{alias}.json")
        return self.keyfile_account_type.write_keyfile(path, secret, passphrase)


class ApeSigner(AccountAPI):
    private_key: PydanticHexStr

    @cached_property
    def address(self) -> AddressType:
        return EthAccount.from_key(self.private_key).address

    @property
    def public_key(self) -> "HexBytes":
        return derive_public_key(HexBytes(self.private_key))

    def sign_authorization(
        self,
        address: AddressType,
        chain_id: int | None = None,
        nonce: int | None = None,
    ) -> MessageSignature | None:
        if chain_id is None:
            chain_id = self.chain_manager.chain_id

        signed_authorization = EthAccount.sign_authorization(
            {
                "chainId": chain_id,
                "address": to_canonical_address(address),
                "nonce": nonce or self.nonce,
            },
            self.private_key,
        )
        return MessageSignature(
            v=signed_authorization.y_parity,
            r=to_bytes(signed_authorization.r),
            s=to_bytes(signed_authorization.s),
        )

    def sign_message(self, msg: Any, **signer_options) -> MessageSignature | None:
        # Convert str and int to SignableMessage if needed
        if isinstance(msg, str):
            msg = encode_defunct(text=msg)
        elif isinstance(msg, int):
            msg = to_hex(msg)
            msg = encode_defunct(hexstr=msg)
        elif isinstance(msg, EIP712Message):
            # Convert EIP712Message to SignableMessage for handling below
            msg = msg.signable_message

        # Process SignableMessage
        if isinstance(msg, SignableMessage):
            signed_msg = EthAccount.sign_message(msg, self.private_key)
            return MessageSignature(
                v=signed_msg.v,
                r=to_bytes(signed_msg.r),
                s=to_bytes(signed_msg.s),
            )

        return None

    def sign_transaction(self, txn: "TransactionAPI", **signer_options) -> "TransactionAPI | None":
        # Signs any transaction that's given to it.
        # NOTE: Using JSON mode, as only primitive types can be signed.
        tx_data = txn.model_dump(mode="json", by_alias=True, exclude={"sender"})
        private_key = PrivateKey(HexBytes(self.private_key))

        # NOTE: var name `sig_r` instead of `r` to avoid clashing with pdb commands.
        try:
            (
                sig_v,
                sig_r,
                sig_s,
                _,
            ) = sign_transaction_dict(private_key, tx_data)
        except TypeError as err:
            # Occurs when missing properties on the txn that are needed to sign.
            raise SignatureError(str(err), transaction=txn) from err

        # NOTE: Using `to_bytes(hexstr=to_hex(sig_r))` instead of `to_bytes(sig_r)` as
        #   a performance optimization.
        txn.signature = TransactionSignature(
            v=sig_v,
            r=to_bytes(hexstr=to_hex(sig_r)),
            s=to_bytes(hexstr=to_hex(sig_s)),
        )

        return txn

    def sign_raw_msghash(self, msghash: HexBytes) -> MessageSignature:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            signed_msg = EthAccount.unsafe_sign_hash(msghash, self.private_key)

        return MessageSignature(
            v=signed_msg.v,
            r=to_bytes(signed_msg.r),
            s=to_bytes(signed_msg.s),
        )

    def set_delegate(self, contract: BaseAddress | AddressType | str, **txn_kwargs):
        contract_address = self.conversion_manager.convert(contract, AddressType)
        sig = self.sign_authorization(contract_address, nonce=self.nonce + 1)
        auth = Authorization.from_signature(
            address=contract_address,
            chain_id=self.chain_manager.chain_id,
            # NOTE: `tx` uses `self.nonce`
            nonce=self.nonce + 1,
            signature=sig,
        )
        tx = self.provider.network.ecosystem.create_transaction(
            type=TransactionType.SET_CODE,
            authorizations=[auth],
            sender=self,
            # NOTE: Cannot target `ZERO_ADDRESS`
            receiver=txn_kwargs.pop("receiver", None) or self,
            **txn_kwargs,
        )
        return self.call(tx)

    def remove_delegate(self, **txn_kwargs):
        sig = self.sign_authorization(ZERO_ADDRESS, nonce=self.nonce + 1)
        auth = Authorization.from_signature(
            chain_id=self.chain_manager.chain_id,
            address=ZERO_ADDRESS,
            # NOTE: `tx` uses `self.nonce`
            nonce=self.nonce + 1,
            signature=sig,
        )
        tx = self.provider.network.ecosystem.create_transaction(
            type=TransactionType.SET_CODE,
            authorizations=[auth],
            sender=self,
            # NOTE: Cannot target `ZERO_ADDRESS`
            receiver=txn_kwargs.pop("receiver", None) or self,
            **txn_kwargs,
        )
        return self.call(tx)


class BaseKeyfileAccount(AccountAPI):
    """
    An account whose secret key lives in an encrypted keyfile.
    """

    keyfile_path: Path
    locked: bool = True
    passphrase_env_prefix: ClassVar[str] = "APE_ACCOUNTS"
    _autosign: bool = False
    _cached_secret: bytes | None = None

    @log_instead_of_fail(default="<BaseKeyfileAccount>")
    def __repr__(self) -> str:
        # NOTE: Prevent errors from preventing repr from working.
        address_str = f" address={self.address}" if self.address else ""
        alias_str = f" alias={self.alias}" if self.alias else ""
        return f"<{self.__class__.__name__}{address_str}{alias_str}>"

    @property
    def alias(self) -> str:
        return self.keyfile_path.stem

    @property
    def keyfile(self) -> dict:
        return json.loads(self.keyfile_path.read_text())

    @classmethod
    def encrypt_secret(cls, secret: bytes, passphrase: str) -> dict:
        """
        The keyfile contents storing ``secret`` encrypted with ``passphrase``.
        """
        return EthAccount.encrypt(secret, passphrase)

    @classmethod
    def write_keyfile(cls, path: Path, secret: bytes, passphrase: str) -> "Self":
        path.write_text(json.dumps(cls.encrypt_secret(secret, passphrase)), encoding="utf8")
        return cls(keyfile_path=path)

    @property
    def _secret(self) -> bytes:
        if self._cached_secret is not None:
            if not self.locked:
                logger.warning("Using cached key for %s", self.alias)
                return self._cached_secret

            self._cached_secret = None

        passphrase = self._prompt_for_passphrase(default="")
        secret = self._decrypt_keyfile(passphrase)
        if click.confirm(f"Leave '{self.alias}' unlocked?"):
            self.locked = False
            self._cached_secret = secret

        return secret

    def unlock(self, passphrase: str | None = None):
        secret: bytes = b""
        if passphrase:
            # NOTE: Try only once, if it fails it was given incorrectly and we should not prompt
            secret = self._decrypt_keyfile(passphrase)

        elif passphrase := environ.get(f"{self.passphrase_env_prefix}_{self.alias}_PASSPHRASE"):
            logger.info(f"Using passphrase for account '{self.alias}' from environment variable")
            # NOTE: Try only once, if it fails then we are non-interactive, so we can't prompt
            secret = self._decrypt_keyfile(passphrase)

        attempts = 1
        while not secret:
            # Passphrase not found, prompt for it up to 3 times.
            passphrase = self._prompt_for_passphrase(
                f"Enter passphrase to permanently unlock '{self.alias}'"
            )
            try:
                secret = self._decrypt_keyfile(passphrase)

            except InvalidPasswordError as err:
                if attempts < 3:
                    logger.error("Invalid password")
                    attempts += 1
                else:
                    raise AccountsError(f"Failed to unlock after {attempts} attempts.") from err

        self._cached_secret = secret
        self.locked = False

    def lock(self):
        self.locked = True

    def change_password(self):
        self.locked = True  # force entering passphrase to get key
        secret = self._secret

        passphrase = self._prompt_for_passphrase("Create new passphrase", confirmation_prompt=True)
        self.keyfile_path.write_text(
            json.dumps(self.encrypt_secret(secret, passphrase)), encoding="utf8"
        )

    def delete(self):
        passphrase = self._prompt_for_passphrase(
            f"Enter passphrase to delete '{self.alias}'", default=""
        )
        self._decrypt_keyfile(passphrase)
        self.keyfile_path.unlink()

    def set_autosign(self, enabled: bool, passphrase: str | None = None):
        """
        Allow this account to automatically sign messages and transactions.

        Args:
            enabled (bool): ``True`` to enable, ``False`` to disable.
            passphrase (str | None): Optionally provide the passphrase.
              If not provided, you will be prompted to enter it.
        """
        if enabled:
            self.unlock(passphrase=passphrase)
            logger.warning("Danger! This account will now sign any transaction it's given.")

        self._autosign = enabled
        if not enabled:
            # Re-lock if it was turning off
            self.locked = True
            self._cached_secret = None

    def _confirm_signing(self, display_msg: str) -> bool:
        return self._autosign or click.confirm(f"{display_msg}\n\nSign: ")

    def _prompt_for_passphrase(self, message: str | None = None, **kwargs) -> str:
        message = message or f"Enter passphrase to unlock '{self.alias}'"
        return click.prompt(
            message,
            hide_input=True,
            **kwargs,
        )

    def _decrypt_keyfile(self, passphrase: str) -> bytes:
        try:
            return EthAccount.decrypt(self.keyfile, passphrase)
        except ValueError as err:
            raise InvalidPasswordError() from err


class KeyfileAccount(BaseKeyfileAccount):
    _autosign_raw_msghash: bool = False

    @property
    def address(self) -> AddressType:
        return self.network_manager.ethereum.decode_address(self.keyfile["address"])

    @property
    def _signer(self) -> ApeSigner:
        return ApeSigner(private_key=self._secret)

    @property
    def public_key(self) -> HexBytes | None:
        keyfile_data = self.keyfile
        if "public_key" in keyfile_data:
            return HexBytes(bytes.fromhex(keyfile_data["public_key"]))

        # Derive the public key from the private key
        public_key = self._signer.public_key
        keyfile_data["public_key"] = remove_0x_prefix(HexStr(public_key.hex()))

        # Store the public key so we don't have to derive it again.
        self.keyfile_path.write_text(json.dumps(keyfile_data), encoding="utf8")

        return public_key

    def sign_authorization(
        self,
        address: AddressType,
        chain_id: int | None = None,
        nonce: int | None = None,
    ) -> MessageSignature | None:
        if chain_id is None:
            chain_id = self.provider.chain_id

        display_msg = f"Allow **full root access** to '{address}' on {chain_id or 'any chain'}?"
        if not click.confirm(click.style(f"{display_msg}\n\nAcknowledge: ", fg="yellow")):
            return None

        return self._signer.sign_authorization(address=address, chain_id=chain_id, nonce=nonce)

    def sign_message(self, msg: Any, **signer_options) -> MessageSignature | None:
        display_msg, msg = _get_signing_message_with_display(msg)
        if display_msg is None:
            logger.warning("Unsupported message type, (type=%r, msg=%r)", type(msg), msg)
            return None

        if self._confirm_signing(display_msg):
            return self._signer.sign_message(msg, **signer_options)

        return None

    def sign_transaction(self, txn: "TransactionAPI", **signer_options) -> "TransactionAPI | None":
        if not self._confirm_signing(f"{txn}"):
            return None

        return self._signer.sign_transaction(txn, **signer_options)

    def sign_raw_msghash(self, msghash: HexBytes) -> MessageSignature | None:
        # NOTE: Signing a raw hash is so dangerous, it only autosigns when explicitly opted in.
        if not self._autosign_raw_msghash:
            logger.warning(
                "Signing a raw hash directly is a dangerous action which could risk "
                "substantial losses! Only confirm if you are 100% sure of the origin!"
            )
            if not click.confirm("Please confirm you wish to sign using `EthAccount.signHash`"):
                return None

        # Ignoring misleading deprecated warning from web3.py.
        # Also, we have already warned the user about the safety.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return self._signer.sign_raw_msghash(msghash)

    def set_autosign(self, enabled: bool, passphrase: str | None = None, raw_msghash: bool = False):
        """
        Allow this account to automatically sign messages and transactions.

        Args:
            enabled (bool): ``True`` to enable, ``False`` to disable.
            passphrase (str | None): Optionally provide the passphrase.
              If not provided, you will be prompted to enter it.
            raw_msghash (bool): ``True`` to also autosign raw message hashes
              (see :meth:`~ape_accounts.accounts.KeyfileAccount.sign_raw_msghash`).
              A raw hash may be a transaction or permit in disguise, so only enable
              this if you trust every hash this account is given.
              Defaults to ``False``.
        """
        super().set_autosign(enabled, passphrase=passphrase)
        if enabled and raw_msghash:
            logger.warning("Danger! This account will now sign any raw message hash it's given.")

        self._autosign_raw_msghash = enabled and raw_msghash

    def set_delegate(self, contract: BaseAddress | AddressType | str, **txn_kwargs):
        return self._signer.set_delegate(contract, **txn_kwargs)

    def remove_delegate(self, **txn_kwargs):
        return self._signer.remove_delegate(**txn_kwargs)


def _write_and_return_account(
    alias: str, passphrase: str, account: "LocalAccount"
) -> KeyfileAccount:
    """Write an account to disk and return an Ape KeyfileAccount"""
    container = ManagerAccessMixin.account_manager.containers["accounts"]
    return cast(KeyfileAccount, container.create_account(alias, passphrase, account.key))


def generate_account(
    alias: str, passphrase: str, hd_path: str = ETHEREUM_DEFAULT_PATH, word_count: int = 12
) -> tuple[KeyfileAccount, str]:
    """
    Generate a new account.

    Args:
        alias (str): The alias name of the account.
        passphrase (str): Passphrase used to encrypt the account storage file.
        hd_path (str): The hierarchical deterministic path to use when generating the account.
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
        hd_path (str): The hierarchical deterministic path to use when generating the account.
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


# Abstracted to make testing easier.
def _get_signing_message_with_display(msg) -> tuple[str | None, Any]:
    display_msg = None

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
        if msg._eip712_domain_.name:
            display_msg += f"\tName: {msg._eip712_domain_.name}\n"
        if msg._eip712_domain_.version:
            display_msg += f"\tVersion: {msg._eip712_domain_.version}\n"
        if msg._eip712_domain_.chainId:
            display_msg += f"\tChain ID: {msg._eip712_domain_.chainId}\n"
        if msg._eip712_domain_.verifyingContract:
            display_msg += f"\tContract: {msg._eip712_domain_.verifyingContract}\n"
        if msg._eip712_domain_.salt:
            display_msg += f"\tSalt: {to_hex(msg._eip712_domain_.salt)}\n"

        # Message Data
        display_msg += "Message\n"
        for field, value in msg.model_dump().items():
            if isinstance(value, dict):
                msg_value = ""
                for sub_field, attr in value.items():
                    if isinstance(attr, bytes):
                        attr = to_hex(attr)

                    msg_value += f"\t\t{sub_field}: {attr}\n"

                display_msg += f"\t{field}:\n{msg_value}\n"

            else:
                if isinstance(value, bytes):
                    value = to_hex(value)

                display_msg += f"\t{field}: {value}\n"

        display_msg = display_msg.strip()
        msg = msg.signable_message

    elif isinstance(msg, SignableMessage):
        display_msg = f"{msg}"

    # Using 2 spaces is cleaner than a full tab.
    if display_msg is not None:
        display_msg = display_msg.replace("\t", "  ")

    return (display_msg, msg)
