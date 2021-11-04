import collections
import json
import os
import re
from copy import deepcopy
from functools import lru_cache
from hashlib import md5
from pathlib import Path
from typing import Any, Dict, List

import yaml
from eth_account import Account
from eth_account.hdaccount import HDPath, seed_from_mnemonic
from hexbytes import HexBytes
from importlib_metadata import PackageNotFoundError, packages_distributions, version

from ape.exceptions import OutOfGasError, TransactionError, VirtualMachineError
from ape.logging import logger

try:
    from functools import cached_property  # type: ignore
except ImportError:
    from backports.cached_property import cached_property  # type: ignore

try:
    from functools import singledispatchmethod  # type: ignore
except ImportError:
    from singledispatchmethod import singledispatchmethod  # type: ignore


@lru_cache(maxsize=None)
def get_distributions():
    return packages_distributions()


def is_relative_to(path: Path, target: Path) -> bool:
    if hasattr(path, "is_relative_to"):
        # NOTE: Only available ``>=3.9``
        return target.is_relative_to(path)  # type: ignore

    else:
        try:
            return target.relative_to(path) is not None
        except ValueError:
            return False


def get_relative_path(target: Path, anchor: Path) -> Path:
    """
    Compute the relative path of ``target`` relative to ``anchor``,
    which may or may not share a common ancestor.
    NOTE: Both paths must be absolute
    """
    if not target.is_absolute():
        raise ValueError("'target' must be an absolute path.")
    if not anchor.is_absolute():
        raise ValueError("'anchor' must be an absolute path.")

    anchor_copy = Path(str(anchor))
    levels_deep = 0
    while not is_relative_to(anchor_copy, target):
        levels_deep += 1
        anchor_copy = anchor_copy.parent

    return Path("/".join(".." for _ in range(levels_deep))).joinpath(
        str(target.relative_to(anchor_copy))
    )


def get_package_version(obj: Any) -> str:
    # If value is already cached/static
    if hasattr(obj, "__version__"):
        return obj.__version__

    # NOTE: In case were don't pass a module name
    if not isinstance(obj, str):
        obj = obj.__name__

    # Reduce module string to base package
    # NOTE: Assumed that string input is module name e.g. ``__name__``
    pkg_name = obj.split(".")[0]

    # NOTE: In case the distribution and package name differ
    dists = get_distributions()
    if pkg_name in dists:
        # NOTE: Shouldn't really be more than 1, but never know
        if len(dists[pkg_name]) != 1:
            logger.warning(f"duplicate pkg_name '{pkg_name}'")
        pkg_name = dists[pkg_name][0]

    try:
        return version(pkg_name)

    except PackageNotFoundError:
        # NOTE: Must handle empty string result here
        return ""


def deep_merge(dict1, dict2):
    """Return a new dictionary by merging two dictionaries recursively."""

    result = deepcopy(dict1)

    for key, value in dict2.items():
        if isinstance(value, collections.Mapping):
            result[key] = deep_merge(result.get(key, {}), value)
        else:
            result[key] = deepcopy(dict2[key])

    return result


def expand_environment_variables(contents: str) -> str:
    return os.path.expandvars(contents)


def load_config(path: Path, expand_envars=True, must_exist=False) -> Dict:
    if path.exists():
        contents = path.read_text()
        if expand_envars:
            contents = expand_environment_variables(contents)

        if path.suffix in (".json",):
            config = json.loads(contents)
        elif path.suffix in (".yml", ".yaml"):
            config = yaml.safe_load(contents)
        else:
            raise TypeError(f"Cannot parse '{path.suffix}' files!")

        return config or {}

    elif must_exist:
        raise OSError(f"{path} does not exist!")

    else:
        return {}


def compute_checksum(source: bytes, algorithm: str = "md5") -> str:
    if algorithm == "md5":
        hasher = md5
    else:
        raise ValueError(f"Unknown algorithm `{algorithm}`.")

    return hasher(source).hexdigest()


GeneratedDevAccount = collections.namedtuple("GeneratedDevAccount", ("address", "private_key"))


def generate_dev_accounts(
    mnemonic,
    number_of_accounts: int = 10,
    hd_path_format="m/44'/60'/0'/{}",
) -> List[GeneratedDevAccount]:
    """
    Creates accounts from the configured test mnemonic.
    Use these accounts (or the mnemonic) in chain-genesis
    for testing providers.
    """
    seed = seed_from_mnemonic(mnemonic, "")
    accounts = []

    for i in range(0, number_of_accounts):
        hd_path = HDPath(hd_path_format.format(i))
        private_key = HexBytes(hd_path.derive(seed)).hex()
        address = Account.from_key(private_key).address
        accounts.append(GeneratedDevAccount(address, private_key))

    return accounts


def get_tx_error_from_web3_value_error(web3_value_error: ValueError) -> TransactionError:
    """
    Returns a custom error from ``ValueError`` from web3.py.
    """
    if not hasattr(web3_value_error, "args") or len(web3_value_error.args) < 1:
        # Not known from provider
        return TransactionError(base_err=web3_value_error)

    err_data = web3_value_error.args[0]
    if not isinstance(err_data, dict):
        return TransactionError(base_err=web3_value_error)

    message = err_data.get("message", json.dumps(err_data))
    code = err_data.get("code")

    if re.match(r"(.*)out of gas(.*)", message.lower()):
        return OutOfGasError(code=code)

    # Try not to raise ``VirtualMachineError`` for any gas-related
    # issues. This is to keep the ``VirtualMachineError`` more focused
    # on contract-application specific faults.
    other_gas_error_patterns = (
        r"(.*)exceeds \w*?[ ]?gas limit(.*)",
        r"(.*)requires at least \d* gas(.*)",
    )
    for pattern in other_gas_error_patterns:
        if re.match(pattern, message.lower()):
            return TransactionError(base_err=web3_value_error, message=message, code=code)

    return VirtualMachineError(message)


__all__ = [
    "cached_property",
    "deep_merge",
    "expand_environment_variables",
    "GeneratedDevAccount",
    "generate_dev_accounts",
    "load_config",
    "singledispatchmethod",
]
