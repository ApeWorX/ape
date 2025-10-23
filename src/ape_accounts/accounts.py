import json
import warnings
from collections.abc import Iterator
from functools import cached_property
from os import environ
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, Union

import click
from eip712.messages import EIP712Message, EIP712Type
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

    from ape.api.transactions import TransactionAPI


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
        chain_id: Optional[int] = None,
        nonce: Optional[int] = None,
    ) -> Optional[MessageSignature]:
        if chain_id is None:
            chain_id = self.provider.chain_id

        signed_authorization = EthAccount.sign_authorization(
            dict(
                chainId=chain_id,
                address=to_canonical_address(address),
                nonce=nonce or self.nonce,
            ),
            self.private_key,
        )
        return MessageSignature(
            v=signed_authorization.y_parity,
            r=to_bytes(signed_authorization.r),
            s=to_bytes(signed_authorization.s),
        )

    def sign_message(self, msg: Any, **signer_options) -> Optional[MessageSignature]:
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

    def sign_transaction(
        self, txn: "TransactionAPI", **signer_options
    ) -> Optional["TransactionAPI"]:
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

    def set_delegate(self, contract: Union[BaseAddress, AddressType, str], **txn_kwargs):
        contract_address = self.conversion_manager.convert(contract, AddressType)
        sig = self.sign_authorization(contract_address, nonce=self.nonce + 1)
        auth = Authorization.from_signature(
            address=contract_address,
            chain_id=self.provider.chain_id,
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
            chain_id=self.provider.chain_id,
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


# NOTE: `AccountAPI` is an BaseInterfaceModel
class KeyfileAccount(AccountAPI):
    keyfile_path: Path
    locked: bool = True
    __autosign: bool = False
    __cached_signer: Optional[ApeSigner] = None

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
    def __signer(self) -> ApeSigner:
        if self.__cached_signer is not None:
            if not self.locked:
                logger.warning("Using cached key for %s", self.alias)
                return self.__cached_signer

            self.__cached_signer = None

        passphrase = self._prompt_for_passphrase(default="")
        key = self.__decrypt_keyfile(passphrase)
        signer = ApeSigner(private_key=key)

        if click.confirm(f"Leave '{self.alias}' unlocked?"):
            self.locked = False
            self.__cached_signer = signer

        return signer

    @property
    def public_key(self) -> Optional[HexBytes]:
        keyfile_data = self.keyfile
        if "public_key" in keyfile_data:
            return HexBytes(bytes.fromhex(keyfile_data["public_key"]))

        # Derive the public key from the private key
        public_key = self.__signer.public_key
        keyfile_data["public_key"] = remove_0x_prefix(HexStr(public_key.hex()))

        # Store the public key so we don't have to derive it again.
        self.keyfile_path.write_text(json.dumps(keyfile_data), encoding="utf8")

        return public_key

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

        if passphrase is None:
            raise AccountsError("Passphrase can't be 'None'")

        # Rest of the code to unlock the account using the passphrase
        self.__cached_signer = ApeSigner(private_key=self.__decrypt_keyfile(passphrase))
        self.locked = False

    def lock(self):
        self.locked = True

    def change_password(self):
        self.locked = True  # force entering passphrase to get key
        key = self.__signer.private_key

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

    def sign_authorization(
        self,
        address: AddressType,
        chain_id: Optional[int] = None,
        nonce: Optional[int] = None,
    ) -> Optional[MessageSignature]:
        if chain_id is None:
            chain_id = self.provider.chain_id

        display_msg = f"Allow **full root access** to '{address}' on {chain_id or 'any chain'}?"
        if not click.confirm(click.style(f"{display_msg}\n\nAcknowledge: ", fg="yellow")):
            return None

        return self.__signer.sign_authorization(address=address, chain_id=chain_id, nonce=nonce)

    def sign_message(self, msg: Any, **signer_options) -> Optional[MessageSignature]:
        display_msg, msg = _get_signing_message_with_display(msg)
        if display_msg is None:
            logger.warning("Unsupported message type, (type=%r, msg=%r)", type(msg), msg)
            return None

        if self.__autosign or click.confirm(f"{display_msg}\n\nSign: "):
            return self.__signer.sign_message(msg, **signer_options)

        return None

    def sign_transaction(
        self, txn: "TransactionAPI", **signer_options
    ) -> Optional["TransactionAPI"]:
        if not (self.__autosign or click.confirm(f"{txn}\n\nSign: ")):
            return None

        return self.__signer.sign_transaction(txn, **signer_options)

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
            return self.__signer.sign_raw_msghash(msghash)

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
            # Re-lock if it was turning off
            self.locked = True
            self.__cached_signer = None

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

    def set_delegate(self, contract: Union[BaseAddress, AddressType, str], **txn_kwargs):
        return self.__signer.set_delegate(contract, **txn_kwargs)

    def remove_delegate(self, **txn_kwargs):
        return self.__signer.remove_delegate(**txn_kwargs)


def _write_and_return_account(
    alias: str, passphrase: str, account: "LocalAccount"
) -> KeyfileAccount:
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
def _get_signing_message_with_display(msg) -> tuple[Optional[str], Any]:
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
            if isinstance(value, EIP712Type):
                msg_fields = [
                    x for x in dir(value) if not x.startswith("_") and not x.startswith("eip712_")
                ]
                msg_value = ""
                for msg_field in msg_fields:
                    attr = getattr(value, msg_field)
                    if isinstance(attr, bytes):
                        attr = to_hex(attr)

                    msg_value += f"\t\t{msg_field}: {attr}\n"

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
