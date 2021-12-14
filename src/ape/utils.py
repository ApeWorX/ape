import collections
import json
import os
import shutil
import sys
import tempfile
import zipfile
from abc import ABCMeta, abstractmethod
from copy import deepcopy
from functools import lru_cache, partial
from hashlib import md5
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Set

import requests
import yaml
from dataclassy import dataclass
from dataclassy.dataclass import DataClassMeta
from eth_account import Account
from eth_account.hdaccount import HDPath, seed_from_mnemonic
from github import Github
from hexbytes import HexBytes
from importlib_metadata import PackageNotFoundError, packages_distributions, version
from tqdm import tqdm  # type: ignore

from ape.exceptions import CompilerError
from ape.logging import logger

try:
    from functools import cached_property  # type: ignore
except ImportError:
    from backports.cached_property import cached_property  # type: ignore

try:
    from functools import singledispatchmethod  # type: ignore
except ImportError:
    from singledispatchmethod import singledispatchmethod  # type: ignore


_python_version = (
    f"{sys.version_info.major}.{sys.version_info.minor}"
    f".{sys.version_info.micro} {sys.version_info.releaselevel}"
)


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

    # NOTE: In case where don't pass a module name
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


__version__ = get_package_version(__name__)
USER_AGENT = f"Ape/{__version__} (Python/{_python_version})"


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
    mnemonic: str,
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


def gas_estimation_error_message(tx_error: Exception) -> str:
    """
    Use this method in ``ProviderAPI`` implementations when error handling
    transaction errors. This is to have a consistent experience across providers.
    """
    return (
        f"Gas estimation failed: '{tx_error}'. This transaction will likely revert. "
        "If you wish to broadcast, you must set the gas limit manually."
    )


def extract_nested_value(root: Mapping, *args: str) -> Optional[Dict]:
    """
    Dig through a nested ``Dict`` gives the keys to use in order as arguments.
    Returns the final value if it exists else `None` if the tree ends at any point.
    """
    current_value: Any = root
    for arg in args:
        if not hasattr(current_value, "get"):
            return None

        current_value = current_value.get(arg)

    return current_value


def stream_response(download_url: str, progress_bar_description: str = "Downloading") -> bytes:
    response = requests.get(download_url, stream=True)
    response.raise_for_status()

    total_size = int(response.headers.get("content-length", 0))
    progress_bar = tqdm(total=total_size, unit="iB", unit_scale=True)
    progress_bar.set_description(progress_bar_description)
    content = bytes()
    for data in response.iter_content(1024, decode_unicode=True):
        progress_bar.update(len(data))
        content += data

    progress_bar.close()
    return content


class GithubClient:
    TOKEN_KEY = "GITHUB_ACCESS_TOKEN"

    def __init__(self):
        token = None
        self.has_auth = self.TOKEN_KEY in os.environ
        if self.has_auth:
            token = os.environ[self.TOKEN_KEY]

        self._client = Github(login_or_token=token, user_agent=USER_AGENT)

    @cached_property
    def ape_org(self):
        return self._client.get_organization("ApeWorX")

    @cached_property
    def available_plugins(self) -> Set[str]:
        return {
            repo.name.replace("-", "_")
            for repo in self.ape_org.get_repos()
            if repo.name.startswith("ape-")
        }

    def get_release(self, repo_path: str, version: str):
        repo = self._client.get_repo(repo_path)

        if not version.startswith("v"):
            version = f"v{version}"

        return repo.get_release(version)

    def download_package(self, repo_path: str, version: str, target_path: Path):
        if not target_path or not target_path.exists() or not target_path.is_dir():
            raise ValueError(f"'target_path' must be a valid directory (got '{target_path}').")

        release = self.get_release(repo_path, version)
        description = f"Downloading {repo_path}@{version}"
        release_content = stream_response(release.zipball_url, progress_bar_description=description)

        # Use temporary path to isolate a package when unzipping
        with tempfile.TemporaryDirectory() as tmp:
            temp_path = Path(tmp)
            with zipfile.ZipFile(BytesIO(release_content)) as zf:
                zf.extractall(temp_path)

            # Copy the directory contents into the target path.
            downloaded_packages = [f for f in temp_path.iterdir() if f.is_dir()]
            if len(downloaded_packages) < 1:
                raise CompilerError(f"Unable to download package at '{repo_path}'.")
            package_path = temp_path / downloaded_packages[0]
            for source_file in package_path.iterdir():
                shutil.move(str(source_file), str(target_path))


github_client = GithubClient()


def get_all_files_in_directory(path: Path) -> List[Path]:
    """
    Returns all the files in a directory structure.

    For example: Given a dir structure like
        dir_a: dir_b, file_a, file_b
        dir_b: file_c

      and you provide the path to `dir_a`, it will return a list containing
      the Paths to `file_a`, `file_b` and `file_c`.
    """
    if path.is_dir():
        return list(path.rglob("*.*"))

    return [path]


class AbstractDataClassMeta(DataClassMeta, ABCMeta):
    pass


abstractdataclass = partial(dataclass, kwargs=True, meta=AbstractDataClassMeta)


__all__ = [
    "abstractdataclass",
    "abstractmethod",
    "AbstractDataClassMeta",
    "cached_property",
    "dataclass",
    "deep_merge",
    "expand_environment_variables",
    "extract_nested_value",
    "get_relative_path",
    "gas_estimation_error_message",
    "get_package_version",
    "github_client",
    "GeneratedDevAccount",
    "generate_dev_accounts",
    "get_all_files_in_directory",
    "load_config",
    "singledispatchmethod",
    "USER_AGENT",
]
