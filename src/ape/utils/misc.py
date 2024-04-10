import asyncio
import functools
import json
import sys
from asyncio import gather
from datetime import datetime
from functools import cached_property, lru_cache, singledispatchmethod, wraps
from importlib.metadata import PackageNotFoundError, distributions
from importlib.metadata import version as version_metadata
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Coroutine, Dict, List, Mapping, Optional, cast

import requests
import yaml
from eth_pydantic_types import HexBytes
from eth_utils import is_0x_prefixed
from packaging.specifiers import SpecifierSet
from tqdm.auto import tqdm  # type: ignore

from ape.exceptions import APINotImplementedError, ProviderNotConnectedError
from ape.logging import logger
from ape.utils.os import expand_environment_variables

if TYPE_CHECKING:
    from ape.types import AddressType


EMPTY_BYTES32 = HexBytes("0x0000000000000000000000000000000000000000000000000000000000000000")
ZERO_ADDRESS: "AddressType" = cast("AddressType", "0x0000000000000000000000000000000000000000")
DEFAULT_TRANSACTION_ACCEPTANCE_TIMEOUT = 120
DEFAULT_LOCAL_TRANSACTION_ACCEPTANCE_TIMEOUT = 20
DEFAULT_LIVE_NETWORK_BASE_FEE_MULTIPLIER = 1.4
DEFAULT_TRANSACTION_TYPE = 0
DEFAULT_MAX_RETRIES_TX = 20

_python_version = (
    f"{sys.version_info.major}.{sys.version_info.minor}"
    f".{sys.version_info.micro} {sys.version_info.releaselevel}"
)


@lru_cache(maxsize=None)
def _get_distributions(pkg_name: Optional[str] = None) -> List:
    """
    Get a mapping of top-level packages to their distributions.
    """

    distros = []
    all_distros = distributions()
    for dist in all_distros:
        package_names = (dist.read_text("top_level.txt") or "").split()
        for name in package_names:
            if pkg_name is None or name == pkg_name:
                distros.append(dist)

    return distros


def pragma_str_to_specifier_set(pragma_str: str) -> Optional[SpecifierSet]:
    """
    Convert the given pragma str to a ``packaging.version.SpecifierSet``
    if possible.

    Args:
        pragma_str (str): The str to convert.

    Returns:
        ``Optional[packaging.version.SpecifierSet]``
    """

    pragma_parts = iter([x.strip(" ,") for x in pragma_str.split(" ")])

    def _to_spec(item: str) -> str:
        item = item.replace("^", "~=")
        if item and item[0].isnumeric():
            return f"=={item}"
        elif item and len(item) >= 2 and item[0] == "=" and item[1] != "=":
            return f"={item}"

        return item

    pragma_parts_fixed = []
    builder = ""
    for sub_part in pragma_parts:
        parts_to_handle: List[str] = []
        if "," in sub_part:
            sub_sub_parts = [x.strip() for x in sub_part.split(",")]
            if len(sub_sub_parts) > 2:
                # Very rare case.
                raise ValueError(f"Cannot handle pragma '{pragma_str}'.")

            if next_part := next(pragma_parts, None):
                parts_to_handle.extend((sub_sub_parts[0], f"{sub_sub_parts[-1]}{next_part}"))
            else:
                # Very rare case.
                raise ValueError(f"Cannot handle pragma '{pragma_str}'.")
        else:
            parts_to_handle.append(sub_part)

        for part in parts_to_handle:
            if not any(c.isnumeric() for c in part):
                # Handle pragma with spaces between constraint and values
                # like `>= 0.6.0`.
                builder += part
                continue
            elif builder:
                spec = _to_spec(f"{builder}{part}")
                builder = ""
            else:
                spec = _to_spec(part)

            pragma_parts_fixed.append(spec)

    try:
        return SpecifierSet(",".join(pragma_parts_fixed))
    except ValueError as err:
        logger.error(str(err))
        return None


def get_package_version(obj: Any) -> str:
    """
    Get the version of a single package.

    Args:
        obj: object to search inside for ``__version__``.

    Returns:
        str: version string.
    """
    # If value is already cached/static
    if hasattr(obj, "__version__"):
        return obj.__version__

    # NOTE: In case where don't pass a module name
    if not isinstance(obj, str) and hasattr(obj, "__name__"):
        obj = obj.__name__

    elif not isinstance(obj, str):
        try:
            str_value = f"{obj}"
        except Exception:
            str_value = "<obj>"

        logger.warning(f"Type issue: Unknown if properly handled {str_value}")

        # Treat as no version found.
        return ""

    # Reduce module string to base package
    # NOTE: Assumed that string input is module name e.g. `__name__`
    pkg_name = obj.split(".")[0]

    # NOTE: In case the distribution and package name differ
    dists = _get_distributions(pkg_name)
    if dists:
        num_packages = len(dists)
        pkg_name = dists[0].metadata["Name"]

        if num_packages != 1:
            # Warn that there are more than 1 package with this name,
            # which can lead to odd behaviors.
            found_paths = [str(d._path) for d in dists if hasattr(d, "_path")]
            found_paths_str = ",\n\t".join(found_paths)
            message = f"Found {num_packages} packages named '{pkg_name}'."
            if found_paths:
                message = f"{message}\nInstallation paths:\n\t{found_paths_str}"

            logger.warning(message)

    try:
        return str(version_metadata(pkg_name))

    except PackageNotFoundError:
        # NOTE: Must handle empty string result here
        return ""


__version__ = get_package_version(__name__)
USER_AGENT = f"Ape/{__version__} (Python/{_python_version})"


def load_config(path: Path, expand_envars=True, must_exist=False) -> Dict:
    """
    Load a configuration file into memory.
    A file at the given path must exist or else it will throw ``OSError``.
    The configuration file must be a `.json` or `.yaml` or else it will throw ``TypeError``.

    Args:
        path (str): path to filesystem to find.
        expand_envars (bool): ``True`` the variables in path
                                are able to expand to show full path.
        must_exist (bool): ``True`` will be set if the configuration file exist
                                and is able to be load.

    Returns:
        Dict (dict): Configured settings parsed from a config file.
    """
    if path.is_file():
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


def gas_estimation_error_message(tx_error: Exception) -> str:
    """
    Get an error message containing the given error and an explanation of how the
    gas estimation failed, as in :class:`ape.api.providers.ProviderAPI` implementations.

    Args:
        tx_error (Exception): The error that occurred when trying to estimate gas.

    Returns:
        str: An error message explaining that the gas failed and that the transaction
        will likely revert.
    """
    txn_error_text = str(tx_error)
    if txn_error_text.endswith("."):
        # Strip period from initial error so it looks better.
        txn_error_text = txn_error_text[:-1]

    return (
        f"Gas estimation failed: '{txn_error_text}'. This transaction will likely revert. "
        "If you wish to broadcast, you must set the gas limit manually."
    )


def extract_nested_value(root: Mapping, *args: str) -> Optional[Dict]:
    """
    Dig through a nested ``dict`` using the given keys and return the
    last-found object.

    Usage example::

            >>> extract_nested_value({"foo": {"bar": {"test": "VALUE"}}}, "foo", "bar", "test")
            'VALUE'

    Args:
        root (dict): Nested keys to form arguments.

    Returns:
        dict, optional: The final value if it exists
        else ``None`` if the tree ends at any point.
    """
    current_value: Any = root
    for arg in args:
        if not hasattr(current_value, "get"):
            return None

        current_value = current_value.get(arg)

    return current_value


def add_padding_to_strings(
    str_list: List[str],
    extra_spaces: int = 0,
    space_character: str = " ",
) -> List[str]:
    """
    Append spacing to each string in a list of strings such that
    they all have the same length.

    Args:
        str_list (List[str]): The list of strings that need padding.
        extra_spaces (int): Optionally append extra spacing. Defaults to ``0``.
        space_character (str): The character to use in the padding. Defaults to ``" "``.

    Returns:
        List[str]: A list of equal-length strings with padded spaces.
    """

    if not str_list:
        return []

    longest_item = len(max(str_list, key=len))
    spaced_items = []

    for value in str_list:
        spacing = (longest_item - len(value) + extra_spaces) * space_character
        spaced_items.append(f"{value}{spacing}")

    return spaced_items


def stream_response(download_url: str, progress_bar_description: str = "Downloading") -> bytes:
    """
    Download HTTP content by streaming and returning the bytes.
    Progress bar will be displayed in the CLI.

    Args:
        download_url (str): String to get files to download.
        progress_bar_description (str): Downloading word.

    Returns:
        bytes: Content in bytes to show the progress.
    """
    response = requests.get(download_url, stream=True)
    response.raise_for_status()

    total_size = int(response.headers.get("content-length", 0))
    progress_bar = tqdm(total=total_size, unit="iB", unit_scale=True, leave=False)
    progress_bar.set_description(progress_bar_description)
    content = b""
    for data in response.iter_content(1024, decode_unicode=True):
        progress_bar.update(len(data))
        content += data

    progress_bar.close()
    return content


def raises_not_implemented(fn):
    """
    Decorator for raising helpful not implemented error.
    """

    def inner(*args, **kwargs):
        raise _create_raises_not_implemented_error(fn)

    return inner


def _create_raises_not_implemented_error(fn):
    return APINotImplementedError(
        f"Attempted to call method '{fn.__qualname__}', method not supported."
    )


def to_int(value) -> int:
    if isinstance(value, int):
        return value
    elif isinstance(value, str):
        return int(value, 16) if is_0x_prefixed(value) else int(value)
    elif isinstance(value, bytes):
        return int.from_bytes(value, "big")

    raise ValueError(f"cannot convert {repr(value)} to int")


def run_until_complete(*item: Any) -> Any:
    """
    Completes the given coroutine and returns its value.

    Args:
        *item (Any): A coroutine or any return value from an async method. If
          not given a coroutine, returns the given item. Provide multiple
          coroutines to run tasks in parallel.

    Returns:
        (Any): The value that results in awaiting the coroutine.
        Else, ``item`` if ``item`` is not a coroutine. If given multiple coroutines,
        returns the result from ``asyncio.gather``.
    """

    items = list(item)
    if not items:
        return None

    elif not isinstance(items[0], Coroutine):
        # Method was marked `async` but didn't return a coroutine.
        # This happens in some `web3.py` methods.
        return items if len(items) > 1 else items[0]

    # Run all coroutines async.
    task = gather(*items, return_exceptions=True) if len(items) > 1 else items[0]
    loop = asyncio.get_event_loop()
    result = loop.run_until_complete(task)
    return result


def allow_disconnected(fn: Callable):
    """
    A decorator that instead of raising :class:`~ape.exceptions.ProviderNotConnectedError`
    warns and returns ``None``.

    Usage example::

        from typing import Optional
        from ape.types import SnapshotID
        from ape.utils import return_none_when_disconnected

        @allow_disconnected
        def try_snapshot(self) -> Optional[SnapshotID]:
            return self.chain.snapshot()

    """

    def inner(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ProviderNotConnectedError:
            logger.warning("Provider is not connected.")
            return None

    return inner


def nonreentrant(key_fn):
    def inner(f):
        locks = set()

        @wraps(f)
        def wrapper(*args, **kwargs):
            key = key_fn(*args, **kwargs)
            if key in locks:
                raise RecursionError(f"nonreentrant {f.__qualname__}:{key}")
            locks.add(key)
            try:
                return f(*args, **kwargs)
            finally:
                locks.discard(key)

        return wrapper

    return inner


def get_current_timestamp_ms() -> int:
    """
    Get the current UNIX timestamp in milliseconds.

    Returns:
        int
    """
    return round(datetime.utcnow().timestamp() * 1000)


def is_evm_precompile(address: str) -> bool:
    """
    Returns ``True`` if the given address string is a known
    Ethereum pre-compile address.

    Args:
        address (str):

    Returns:
        bool
    """
    try:
        address = address.replace("0x", "")
        return 0 < sum(int(x) for x in address) < 10
    except Exception:
        return False


def is_zero_hex(address: str) -> bool:
    """
    Returns ``True`` if the hex str is only zero.
    **NOTE**: Empty hexes like ``"0x"`` are considered zero.

    Args:
        address (str): The address to check.

    Returns:
        bool
    """

    try:
        if addr := address.replace("0x", ""):
            return sum(int(x) for x in addr) == 0
        else:
            # "0x" counts as zero.
            return True

    except Exception:
        return False


def _dict_overlay(mapping: Dict[str, Any], overlay: Dict[str, Any], depth: int = 0):
    """Overlay given overlay structure on a dict"""
    for key, value in overlay.items():
        if isinstance(value, dict):
            if key not in mapping:
                mapping[key] = dict()
            _dict_overlay(mapping[key], value, depth + 1)
        else:
            mapping[key] = value
    return mapping


def log_instead_of_fail(default: Optional[Any] = None):
    """
    A decorator for logging errors instead of raising.
    This is useful for methods like __repr__ which shouldn't fail.
    """

    def wrapper(fn):
        @functools.wraps(fn)
        def wrapped(*args, **kwargs):
            try:
                if args and isinstance(args[0], type):
                    return fn(*args, **kwargs)
                else:
                    return fn(*args, **kwargs)

            except Exception as err:
                logger.error(str(err))
                if default:
                    return default

        return wrapped

    return wrapper


__all__ = [
    "allow_disconnected",
    "cached_property",
    "_dict_overlay",
    "extract_nested_value",
    "gas_estimation_error_message",
    "get_current_timestamp_ms",
    "pragma_str_to_specifier_set",
    "get_package_version",
    "is_evm_precompile",
    "is_zero_hex",
    "load_config",
    "log_instead_of_fail",
    "nonreentrant",
    "raises_not_implemented",
    "run_until_complete",
    "singledispatchmethod",
    "stream_response",
    "USER_AGENT",
]
