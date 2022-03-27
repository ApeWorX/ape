import json
import os
import re
import shutil
import sys
import tempfile
import zipfile
from abc import ABC, abstractmethod
from collections import namedtuple
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Dict, List, Mapping, Optional, Set, cast

import pygit2  # type: ignore
import requests
import yaml
from eth_account import Account
from eth_account.hdaccount import HDPath, seed_from_mnemonic
from eth_utils import to_checksum_address as to_address
from github import Github, UnknownObjectException
from github.GitRelease import GitRelease
from github.Organization import Organization
from github.Repository import Repository as GithubRepository
from hexbytes import HexBytes
from importlib_metadata import PackageNotFoundError, packages_distributions
from importlib_metadata import version as version_metadata
from pydantic import BaseModel
from pygit2 import Repository as GitRepository
from tqdm import tqdm  # type: ignore

from ape.exceptions import CompilerError, ProjectError, ProviderNotConnectedError
from ape.logging import logger
from ape.types import AddressType

try:
    from functools import cached_property  # type: ignore
except ImportError:
    from backports.cached_property import cached_property  # type: ignore
try:
    from functools import singledispatchmethod  # type: ignore
except ImportError:
    from singledispatchmethod import singledispatchmethod  # type: ignore

if TYPE_CHECKING:
    from ape.api.providers import ProviderAPI
    from ape.contracts.base import ContractContainer, ContractInstance, ContractType
    from ape.managers.accounts import AccountManager
    from ape.managers.chain import ChainManager
    from ape.managers.compilers import CompilerManager
    from ape.managers.config import ConfigManager
    from ape.managers.converters import ConversionManager
    from ape.managers.networks import NetworkManager
    from ape.managers.project import DependencyManager, ProjectManager
    from ape.managers.query import QueryManager
    from ape.plugins import PluginManager


DEFAULT_NUMBER_OF_TEST_ACCOUNTS = 10
DEFAULT_TEST_MNEMONIC = "test test test test test test test test test test test junk"

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


def is_relative_to(path: Path, target: Path) -> bool:
    """
    Search a path and determine its relevancy.

    Args:
        path (str): Path represents a filesystem to find.
        target (str): Path represents a filesystem to match.

    Returns:
        bool: ``True`` if the path is relative to the target path or ``False``.
    """
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
    **NOTE**: Both paths must be absolute.

    Args:
        target (pathlib.Path): The path we are interested in.
        anchor (pathlib.Path): The path we are starting from.

    Returns:
        pathlib.Path: The new path to the target path from the anchor path.
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


class use_temp_sys_path:
    """
    A context manager to manage injecting and removing paths from
    a user's sys paths without permanently modifying it.
    """

    def __init__(self, path: Path):
        self.temp_path = str(path)

    def __enter__(self):
        sys.path.append(self.temp_path)

    def __exit__(self, *exc):
        sys.path.remove(self.temp_path)


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
        return str(version_metadata(pkg_name))

    except PackageNotFoundError:
        # NOTE: Must handle empty string result here
        return ""


__version__ = get_package_version(__name__)
USER_AGENT = f"Ape/{__version__} (Python/{_python_version})"


def expand_environment_variables(contents: str) -> str:
    """
    Replace substrings of the form ``$name`` or ``${name}`` in the given path
    with the value of environment variable name.

    Args:
        contents (str): A path-like object representing a file system.
                            A path-like object is either a string or bytes object
                            representing a path.
    Returns:
        str: The given content with all environment variables replaced with their values.
    """
    return os.path.expandvars(contents)


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


GeneratedDevAccount = namedtuple("GeneratedDevAccount", ("address", "private_key"))
"""
An account key-pair generated from the test mnemonic. Set the test mnemonic
in your ``ape-config.yaml`` file under the ``test`` section. Access your test
accounts using the :py:attr:`~ape.managers.accounts.AccountManager.test_accounts` property.

Config example::

    test:
      mnemonic: test test test test test test test test test test test junk
      number_of_accounts: 10

"""


def generate_dev_accounts(
    mnemonic: str = DEFAULT_TEST_MNEMONIC,
    number_of_accounts: int = DEFAULT_NUMBER_OF_TEST_ACCOUNTS,
    hd_path_format="m/44'/60'/0'/{}",
) -> List[GeneratedDevAccount]:
    """
    Create accounts from the given test mnemonic.
    Use these accounts (or the mnemonic) in chain-genesis
    for testing providers.

    Args:
        mnemonic (str): mnemonic phrase or seed words.
        number_of_accounts (int): Number of accounts. Defaults to ``10``.
        hd_path_format (str): Hard Wallets/HD Keys derivation path format.
          Defaults to ``"m/44'/60'/0'/{}"``.

    Returns:
        List[:class:`~ape.utils.GeneratedDevAccount`]: List of development accounts.
    """
    seed = seed_from_mnemonic(mnemonic, "")
    accounts = []

    for i in range(number_of_accounts):
        hd_path = HDPath(hd_path_format.format(i))
        private_key = HexBytes(hd_path.derive(seed)).hex()
        address = Account.from_key(private_key).address
        accounts.append(GeneratedDevAccount(address, private_key))

    return accounts


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
    return (
        f"Gas estimation failed: '{tx_error}'. This transaction will likely revert. "
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
    progress_bar = tqdm(total=total_size, unit="iB", unit_scale=True)
    progress_bar.set_description(progress_bar_description)
    content = bytes()
    for data in response.iter_content(1024, decode_unicode=True):
        progress_bar.update(len(data))
        content += data

    progress_bar.close()
    return content


class GithubClient:
    """
    An HTTP client for the Github API.
    """

    TOKEN_KEY = "GITHUB_ACCESS_TOKEN"
    _repo_cache: Dict[str, GithubRepository] = {}

    def __init__(self):
        token = os.environ[self.TOKEN_KEY] if self.TOKEN_KEY in os.environ else None
        self._client = Github(login_or_token=token, user_agent=USER_AGENT)

    @cached_property
    def ape_org(self) -> Organization:
        """
        The ``ApeWorX`` organization on ``Github`` (https://github.com/ApeWorX).
        """
        return self._client.get_organization("ApeWorX")

    @cached_property
    def available_plugins(self) -> Set[str]:
        """
        The available ``ape`` plugins, found from looking at the ``ApeWorx`` Github organization.

        Returns:
            Set[str]: The plugin names as ``'ape_plugin_name'`` (module-like).
        """
        return {
            repo.name.replace("-", "_")
            for repo in self.ape_org.get_repos()
            if not repo.private and repo.name.startswith("ape-")
        }

    def get_release(self, repo_path: str, version: str) -> GitRelease:
        """
        Get a release from Github.

        Args:
            repo_path (str): The path on Github to the repository,
              e.g. ``OpenZeppelin/openzeppelin-contracts``.
            version (str): The version of the release to get. Pass in ``"latest"``
              to get the latest release.

        Returns:
            github.GitRelease.GitRelease
        """
        repo = self._client.get_repo(repo_path)

        if version == "latest":
            return repo.get_latest_release()

        if not version.startswith("v"):
            version = f"v{version}"

        try:
            return repo.get_release(version)
        except UnknownObjectException:
            raise ProjectError(f"Unknown version '{version.lstrip('v')}' for repo '{repo.name}'.")

    def get_repo(self, repo_path: str) -> GithubRepository:
        """
        Get a repository from GitHub.

        Args:
            repo_path (str): The path to the repository, such as
              ``OpenZeppelin/openzeppelin-contracts``.

        Returns:
            github.Repository.Repository
        """

        if repo_path not in self._repo_cache:
            try:
                self._repo_cache[repo_path] = self._client.get_repo(repo_path)
                return self._repo_cache[repo_path]
            except UnknownObjectException as err:
                raise ProjectError(f"Unknown repository '{repo_path}'") from err

        else:
            return self._repo_cache[repo_path]

    def clone_repo(
        self, repo_path: str, target_path: Path, branch: Optional[str] = None
    ) -> GitRepository:
        """
        Clone a repository from Github.

        Args:
            repo_path (str): The path on Github to the repository,
              e.g. ``OpenZeppelin/openzeppelin-contracts``.
            target_path (Path): The local path to store the repo.
            branch (Optional[str]): The branch to clone. Defaults to the default branch.

        Returns:
            pygit2.repository.Repository
        """

        repo = self.get_repo(repo_path)
        branch = branch or repo.default_branch
        logger.info(f"Cloning branch '{branch}' from '{repo.name}'.")

        class GitRemoteCallbacks(pygit2.RemoteCallbacks):
            PERCENTAGE_PATTERN = r"[1-9]{1,2}% \([1-9]*/[1-9]*\)"  # e.g. '75% (324/432)'
            total_objects: int = 0
            current_objects_cloned: int = 0
            _progress_bar = None

            def sideband_progress(self, string: str):
                # Parse a line like 'Compressing objects:   0% (1/432)'
                string = string.lower()
                expected_prefix = "compressing objects:"
                if expected_prefix not in string:
                    return

                progress_str = string.split(expected_prefix)[-1].strip()

                if not re.match(self.PERCENTAGE_PATTERN, progress_str):
                    return None

                progress_parts = progress_str.split(" ")
                fraction_str = progress_parts[1].lstrip("(").rstrip(")")
                fraction = fraction_str.split("/")

                GitRemoteCallbacks.total_objects = int(fraction[1])
                previous_value = GitRemoteCallbacks.current_objects_cloned
                new_value = int(fraction[0])
                GitRemoteCallbacks.current_objects_cloned = new_value

                if GitRemoteCallbacks.total_objects and not GitRemoteCallbacks._progress_bar:
                    GitRemoteCallbacks._progress_bar = tqdm(range(GitRemoteCallbacks.total_objects))

                difference = new_value - previous_value
                if difference > 0:
                    GitRemoteCallbacks._progress_bar.update(difference)  # type: ignore
                    GitRemoteCallbacks._progress_bar.refresh()  # type: ignore

        clone = pygit2.clone_repository(
            repo.git_url, str(target_path), checkout_branch=branch, callbacks=GitRemoteCallbacks()
        )
        return clone

    def download_package(self, repo_path: str, version: str, target_path: Path):
        """
        Download a package from Github. This is useful for managing project dependencies.

        Args:
            repo_path (str): The path on ``Github`` to the repository,
                                such as ``OpenZeppelin/openzeppelin-contracts``.
            version (str): Number to specify update types
                                to the downloaded package.
            target_path (path): A path in your local filesystem to save the downloaded package.
        """
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

    For example, given a directory structure like::

        dir_a: dir_b, file_a, file_b
        dir_b: file_c

    and you provide the path to ``dir_a``, it will return a list containing
    the paths to ``file_a``, ``file_b`` and ``file_c``.

    Args:
        path (pathlib.Path): A directory containing files of interest.

    Returns:
        List[pathlib.Path]: A list of files in the given directory.
    """
    if not path.exists():
        return []

    if path.is_dir():
        return [p for p in list(path.rglob("*.*")) if not p.is_dir() and p.exists()]

    return [path]


class injected_before_use(property):
    """
    Injected properties are injected class variables that must be set before use
    **NOTE**: do not appear in a Pydantic model's set of properties.
    """

    def __get__(self, *args):
        raise ValueError("Value not set. Please inject this property before calling.")


class ManagerAccessMixin:

    # NOTE: cast is used to update the class type returned to mypy
    account_manager: ClassVar["AccountManager"] = cast("AccountManager", injected_before_use())

    chain_manager: ClassVar["ChainManager"] = cast("ChainManager", injected_before_use())

    compiler_manager: ClassVar["CompilerManager"] = cast("CompilerManager", injected_before_use())

    config_manager: ClassVar["ConfigManager"] = cast("ConfigManager", injected_before_use())

    conversion_manager: ClassVar["ConversionManager"] = cast(
        "ConversionManager", injected_before_use()
    )

    dependency_manager: ClassVar["DependencyManager"] = cast(
        "DependencyManager", injected_before_use()
    )

    network_manager: ClassVar["NetworkManager"] = cast("NetworkManager", injected_before_use())

    plugin_manager: ClassVar["PluginManager"] = cast("PluginManager", injected_before_use())

    project_manager: ClassVar["ProjectManager"] = cast("ProjectManager", injected_before_use())

    query_manager: ClassVar["QueryManager"] = cast("QueryManager", injected_before_use())

    @property
    def provider(self) -> "ProviderAPI":
        """
        The current active provider if connected to one.

        Raises:
            :class:`~ape.exceptions.AddressError`: When there is no active
               provider at runtime.

        Returns:
            :class:`~ape.api.providers.ProviderAPI`
        """
        if self.network_manager.active_provider is None:
            raise ProviderNotConnectedError()
        return self.network_manager.active_provider

    def create_contract_container(self, contract_type: "ContractType") -> "ContractContainer":
        """
        Helper method for creating a ``ContractContainer``.

        Args:
            contract_type (``ContractType``): Type of contract for the container

        Returns:
            :class:`~ape.contracts.ContractContainer`
        """
        from ape.contracts.base import ContractContainer

        return ContractContainer(contract_type=contract_type)

    def create_contract(
        self, address: "AddressType", contract_type: "ContractType"
    ) -> "ContractInstance":
        """
        Helper method for creating a ``ContractInstance``.

        Args:
            address (``AddressType``): Address of contract
            contract_type (``ContractType``): Type of contract

        Returns:
            :class:`~ape.contracts.ContractInstance`
        """
        from ape.contracts.base import ContractInstance

        return ContractInstance(address=address, contract_type=contract_type)


class BaseInterface(ManagerAccessMixin, ABC):
    """
    Abstract class that has manager access.
    """


class BaseInterfaceModel(BaseInterface, BaseModel):
    """
    An abstract base-class with manager access on a pydantic base model.
    """

    class Config:
        # NOTE: Due to https://github.com/samuelcolvin/pydantic/issues/1241 we have
        # to add this cached property workaround in order to avoid this error:

        #    TypeError: cannot pickle '_thread.RLock' object

        keep_untouched = (cached_property, singledispatchmethod)
        arbitrary_types_allowed = True
        underscore_attrs_are_private = True
        anystr_strip_whitespace = True

    def __dir__(self) -> List[str]:
        """
        NOTE: Should integrate options in IPython tab-completion.
        https://ipython.readthedocs.io/en/stable/config/integrating.html
        """
        # Filter out protected/private members
        return [member for member in super().__dir__() if not member.startswith("_")]

    def dict(self, *args, **kwargs) -> Dict:
        if "by_alias" not in kwargs:
            kwargs["by_alias"] = True

        if "exclude_none" not in kwargs:
            kwargs["exclude_none"] = True

        return super().dict(*args, **kwargs)

    def json(self, *args, **kwargs) -> str:

        if "separators" not in kwargs:
            kwargs["separators"] = (",", ":")

        if "sort_keys" not in kwargs:
            kwargs["sort_keys"] = True

        if "by_alias" not in kwargs:
            kwargs["by_alias"] = True

        if "exclude_none" not in kwargs:
            kwargs["exclude_none"] = True

        return super().json(*args, **kwargs)


def raises_not_implemented(fn):
    """
    Decorator for raising helpful not implemented error.
    """

    def inner(*args, **kwargs):
        raise NotImplementedError(
            f"Attempted to call method '{fn.__qualname__}', method not supported."
        )

    return inner


__all__ = [
    "abstractmethod",
    "BaseInterfaceModel",
    "cached_property",
    "expand_environment_variables",
    "extract_nested_value",
    "get_relative_path",
    "gas_estimation_error_message",
    "get_package_version",
    "github_client",
    "GeneratedDevAccount",
    "generate_dev_accounts",
    "get_all_files_in_directory",
    "injected_before_use",
    "load_config",
    "raises_not_implemented",
    "singledispatchmethod",
    "stream_response",
    "to_address",
    "USER_AGENT",
]
