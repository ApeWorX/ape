import asyncio
import json
import sys
from functools import cached_property, lru_cache, singledispatchmethod
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, List, Mapping, Optional

import requests
import yaml
from hexbytes import HexBytes
from importlib_metadata import PackageNotFoundError, distributions, packages_distributions
from importlib_metadata import version as version_metadata
from tqdm.auto import tqdm  # type: ignore

from ape.exceptions import APINotImplementedError, ProviderNotConnectedError
from ape.logging import logger
from ape.utils.os import expand_environment_variables

EMPTY_BYTES32 = HexBytes("0x0000000000000000000000000000000000000000000000000000000000000000")
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
DEFAULT_TRANSACTION_ACCEPTANCE_TIMEOUT = 120
DEFAULT_LOCAL_TRANSACTION_ACCEPTANCE_TIMEOUT = 20

_python_version = (
    f"{sys.version_info.major}.{sys.version_info.minor}"
    f".{sys.version_info.micro} {sys.version_info.releaselevel}"
)


@lru_cache(maxsize=None)
def get_distributions():
    """
    Get a mapping of top-level packages to their distributions.
    """

    return packages_distributions()


@lru_cache(maxsize=None)
def _get_distributions(pkg_name: str) -> List:
    """
    Get a mapping of top-level packages to their distributions.
    """

    distros = []
    all_distros = distributions()
    for dist in all_distros:
        package_names = (dist.read_text("top_level.txt") or "").split()
        for name in package_names:
            if name == pkg_name:
                distros.append(dist)

    return distros


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
    if not isinstance(obj, str):
        obj = obj.__name__

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
        raise APINotImplementedError(
            f"Attempted to call method '{fn.__qualname__}', method not supported."
        )

    return inner


def to_int(value) -> int:
    if isinstance(value, int):
        return value
    elif isinstance(value, str):
        if value.startswith("0x"):
            return int(value, 16)
        else:
            return int(value)
    elif isinstance(value, bytes):
        return int.from_bytes(value, "big")

    raise ValueError(f"cannot convert {repr(value)} to int")


def run_until_complete(item: Any) -> Any:
    """
    Completes the given coroutine and returns its value.

    Args:
        item (Any): A return value from a potentially async method.

    Returns:
        (Any): The value that results in awaiting the coroutine.
          Else, ``item`` if ``item`` is not a coroutine.
    """

    if not isinstance(item, Coroutine):
        return item

    loop = asyncio.get_event_loop()
    return loop.run_until_complete(item)


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


__all__ = [
    "allow_disconnected",
    "cached_property",
    "extract_nested_value",
    "gas_estimation_error_message",
    "get_package_version",
    "load_config",
    "raises_not_implemented",
    "run_until_complete",
    "singledispatchmethod",
    "stream_response",
    "USER_AGENT",
]
