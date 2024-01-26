"""Base non-pydantic validator utils"""
from eth_utils import is_hex

from ape.exceptions import AccountsError, AliasAlreadyInUseError
from ape.utils.basemodel import ManagerAccessMixin


def _validate_account_alias(alias: str) -> str:
    """Validate an account alias"""
    if alias in ManagerAccessMixin.account_manager.aliases:
        raise AliasAlreadyInUseError(alias)
    elif not isinstance(alias, str):
        raise AccountsError(f"Alias must be a str, not '{type(alias)}'.")
    elif is_hex(alias) and len(alias) >= 42:
        # Prevents private keys from accidentally being stored in plaintext
        # Ref: https://github.com/ApeWorX/ape/issues/1525
        raise AccountsError("Longer aliases cannot be hex strings.")

    return alias


def _validate_account_passphrase(passphrase: str) -> str:
    """Make sure given passphrase is valid for account encryption"""
    if not passphrase or not isinstance(passphrase, str):
        raise AccountsError("Account file encryption passphrase must be provided.")

    # TODO: Implement length and complexity checks?

    return passphrase


__all__ = ["_validate_account_alias", "_validate_account_passphrase"]
