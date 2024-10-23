import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Optional, Union

import pytest
from click.testing import CliRunner
from ethpm_types import ContractType

import ape
from ape.contracts import ContractContainer
from ape.logging import LogLevel, logger
from ape.managers.project import Project
from ape.pytest.config import ConfigWrapper
from ape.pytest.gas import GasTracker
from ape.types.address import AddressType
from ape.types.units import CurrencyValue
from ape.utils.basemodel import only_raise_attribute_error
from ape.utils.misc import ZERO_ADDRESS
from ape.utils.testing import DEFAULT_TEST_CHAIN_ID

# Needed to test tracing support in core `ape test` command.
pytest_plugins = ["pytester"]
GETH_URI = "http://127.0.0.1:5550"
ALIAS = "__FUNCTIONAL_TESTS_ALIAS__"
geth_process_test = pytest.mark.xdist_group(name="geth-tests")
explorer_test = pytest.mark.xdist_group(name="explorer-tests")

# Ensure we don't persist any .ape data or using existing.

_DATA_FOLDER_CTX = ape.config.isolate_data_folder()
DATA_FOLDER = _DATA_FOLDER_CTX.__enter__()
ape.config.DATA_FOLDER = DATA_FOLDER
SHARED_CONTRACTS_FOLDER = (
    Path(__file__).parent / "functional" / "data" / "contracts" / "ethereum" / "local"
)


EXPECTED_MYSTRUCT_C = 244
"""Hardcoded everywhere in contracts."""


def pytest_addoption(parser):
    parser.addoption(
        "--includepip", action="store_true", help="run tests that depend on pip install operations"
    )


def pytest_runtest_setup(item):
    if "pip" in item.keywords and not item.config.getoption("--includepip"):
        pytest.skip("need --includepip option to run this test")


@pytest.fixture(autouse=True)
def setenviron(monkeypatch):
    """
    Sets the APE_TESTING environment variable during tests.

    With this variable set fault handling and IPython command history logging
    will be disabled in the ape console.
    """
    monkeypatch.setenv("APE_TESTING", "1")


@pytest.fixture(scope="session", autouse=True)
def clean_temp_data_folder():
    yield
    _DATA_FOLDER_CTX.__exit__(None, None, None)


@pytest.fixture(scope="session", autouse=True)
def start_dir():
    return os.getcwd()


@pytest.fixture(autouse=True)
def validate_cwd(start_dir):
    # Handle weird issues with cwd breaking everything.
    # Possibly dur to chdir to a tempdir and then it gets deleted. my guess.
    # TODO: Find root cause and fix there.
    try:
        os.getcwd()
    except Exception:
        # Change back to project root, hopefully.
        os.chdir(start_dir)


@pytest.fixture
def example_project():
    path = "tests/functional/data/contracts/ethereum/local"
    with ape.project.temp_config(contracts_folder=path):
        ape.project.clean()
        yield ape.project
        ape.project.clean()


@pytest.fixture(scope="session")
def config():
    return ape.config


@pytest.fixture(scope="session")
def conversion_manager(chain):
    return chain.conversion_manager


@pytest.fixture(scope="session")
def convert(conversion_manager):
    return conversion_manager.convert


@pytest.fixture(scope="session")
def data_folder(config):
    return DATA_FOLDER


@pytest.fixture(scope="session")
def projects_path():
    return Path(__file__).parent / "integration" / "cli" / "projects"


@pytest.fixture(scope="session")
def with_dependencies_project_path(projects_path):
    return projects_path / "with-dependencies"


@pytest.fixture(scope="session")
def plugin_manager():
    return ape.networks.plugin_manager


@pytest.fixture(scope="session")
def account_manager():
    # NOTE: `accounts` fixture comes with ape_test as the test-accounts.
    return ape.accounts


@pytest.fixture(scope="session")
def compilers():
    return ape.compilers


@pytest.fixture(scope="session")
def owner(accounts):
    return accounts[0]


@pytest.fixture(scope="session")
def sender(accounts):
    return accounts[1]


@pytest.fixture(scope="session")
def receiver(accounts):
    return accounts[2]


@pytest.fixture(scope="session")
def not_owner(accounts):
    return accounts[3]


@pytest.fixture(scope="session")
def helper(accounts):
    return accounts[4]


@pytest.fixture(scope="session")
def mystruct_c():
    return CurrencyValue(EXPECTED_MYSTRUCT_C)


@pytest.fixture
def signer(accounts):
    return accounts[5]


@pytest.fixture
def geth_account(accounts):
    return accounts[6]


@pytest.fixture
def geth_second_account(accounts):
    return accounts[7]


@pytest.fixture(scope="session")
def keyparams():
    # NOTE: password is 'asdf1234'
    return {
        "address": "f39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
        "crypto": {
            "cipher": "aes-128-ctr",
            "cipherparams": {"iv": "229df0a8949798c192caf21531b64a01"},
            "ciphertext": "c68e03a33ab139a4822f578d76452658c13a0ea370f3c997651613dea8925483",
            "kdf": "scrypt",
            "kdfparams": {
                "dklen": 32,
                "n": 262144,
                "r": 8,
                "p": 1,
                "salt": "e1f01ece5afa9819e0ff6c1761737c68",
            },
            "mac": "10ee5db98f1a653c9bda7657f3b3b8bd55dd2fec93936e6b1783af912f9167c2",
        },
        "id": "1af390c5-c4cf-46d0-9341-5374e1a84959",
        "version": 3,
    }


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def networks_disconnected():
    provider = ape.networks.active_provider
    ape.networks.active_provider = None

    try:
        yield ape.networks
    finally:
        ape.networks.active_provider = provider


@pytest.fixture
def ethereum(networks):
    return networks.ethereum


@pytest.fixture(autouse=True)
def eth_tester_provider(ethereum):
    # NOTE: Ensure it uses the default instance of eth-tester.
    with ethereum.local.use_provider(
        "test", provider_settings={"chain_id": DEFAULT_TEST_CHAIN_ID}
    ) as provider:
        yield provider


@pytest.fixture
def mock_provider(mock_web3, eth_tester_provider):
    web3 = eth_tester_provider.web3
    eth_tester_provider._web3 = mock_web3
    yield eth_tester_provider
    eth_tester_provider._web3 = web3


@pytest.fixture
def networks_connected_to_tester(eth_tester_provider):
    return eth_tester_provider.network_manager


@pytest.fixture
def geth_provider(networks):
    if (
        not networks.active_provider
        or networks.provider.name != "node"
        or networks.network.name != "local"
        or not networks.provider.is_connected
        or getattr(networks.provider, "uri", "") != GETH_URI
    ):
        test_acct_100 = "0x63c7f11162dBFC374DC6f5C0B3Aa26C618846a85"
        with networks.ethereum.local.use_provider(
            "node", provider_settings={"uri": GETH_URI, "extra_funded_accounts": [test_acct_100]}
        ) as provider:
            yield provider
    else:
        yield networks.provider


@pytest.fixture
def empty_data_folder():
    # Avoid user's global ape-config data.
    if "global_config" in (ape.config.__dict__ or {}):
        del ape.config.__dict__["global_config"]

    shutil.rmtree(DATA_FOLDER, ignore_errors=True)
    DATA_FOLDER.mkdir(parents=True, exist_ok=True)
    yield


@pytest.fixture
def keyfile_account(owner, keyparams, temp_keyfile_account_ctx):
    with temp_keyfile_account_ctx(ALIAS, keyparams, owner) as account:
        # Ensure starts off locked.
        account.lock()
        yield account


@pytest.fixture
def temp_keyfile_account_ctx():
    @contextmanager
    def _temp_keyfile_account(alias: str, keyparams, sender):
        accts_folder = DATA_FOLDER / "accounts"
        accts_folder.mkdir(parents=True, exist_ok=True)
        test_keyfile_path = accts_folder / f"{alias}.json"

        if test_keyfile_path.is_file():
            account = ape.accounts.load(ALIAS)
        else:
            account = _make_keyfile_account(accts_folder, alias, keyparams, sender)

        try:
            yield account
        finally:
            if test_keyfile_path.is_file():
                test_keyfile_path.unlink()

    return _temp_keyfile_account


def _make_keyfile_account(base_path: Path, alias: str, params: dict, funder):
    test_keyfile_path = base_path / f"{alias}.json"

    if test_keyfile_path.is_file():
        # Corrupted from a previous test
        test_keyfile_path.unlink()

    test_keyfile_path.write_text(json.dumps(params), encoding="utf8")
    acct = ape.accounts.load(alias)
    funder.transfer(acct, "25 ETH")  # Auto-fund this account
    return acct


def skip_if_plugin_installed(*plugin_names: str):
    """
    A simple decorator for skipping a test if a plugin is installed.
    **NOTE**: For performance reasons, this method is not very good.
    It only works for common ApeWorX supported plugins and is only
    meant for assisting testing in Core (NOT a public utility).
    """
    names = [n.lower().replace("-", "_").replace("ape_", "") for n in plugin_names]
    msg_f = "Cannot run this test when plugin '{}' installed."

    def wrapper(fn):
        for name in names:
            # Compilers
            if name in ("solidity", "vyper"):
                compiler = ape.compilers.get_compiler(name)
                if compiler:

                    def test_skip_from_compiler(*args, **kwargs):
                        pytest.mark.skip(msg_f.format(name))

                    # NOTE: By returning a function, we avoid a collection warning.
                    return test_skip_from_compiler

            # Converters
            elif name in ("ens",):
                address_converters = [
                    type(n).__name__ for n in ape.chain.conversion_manager._converters[AddressType]
                ]
                if any(x.startswith(name.upper()) for x in address_converters):

                    def test_skip_from_converter():
                        pytest.mark.skip(msg_f.format(name))

                    return test_skip_from_converter
        # noop
        return fn

    return wrapper


@pytest.fixture
def zero_address():
    return ZERO_ADDRESS


@pytest.fixture
def ape_caplog(caplog):
    class ApeCaplog:
        def __init__(self, caplog_level: LogLevel = LogLevel.WARNING):
            self.level = caplog_level
            self.messages_at_start = list(caplog.messages)
            self.set_levels(caplog_level=caplog_level)

        @only_raise_attribute_error
        def __getattr__(self, name: str) -> Any:
            return getattr(caplog, name)

        @contextmanager
        def at_level(self, level: LogLevel):
            original = self.level
            self.set_levels(level)
            yield
            self.set_levels(original)

        @property
        def fail_message(self) -> str:
            if caplog.messages:
                last_message = caplog.messages[-1]
                return f"Actual last message: {last_message}"

            elif self.messages_at_start:
                return (
                    f"Failed to detect logs. "
                    f"However, we did have logs before the operation: "
                    f"{', '.join(self.messages_at_start)}"
                )

            else:
                return "No logs found!"

        @property
        def head(self) -> str:
            """
            A str representing the latest logged line.
            Initialized to empty str.
            """
            return caplog.messages[-1] if len(caplog.messages) else ""

        def set_levels(self, caplog_level: LogLevel = LogLevel.WARNING):
            self.level = caplog_level
            logger.set_level(LogLevel.INFO)
            caplog.set_level(caplog_level)

        def assert_last_log(self, message: str):
            assert message in self.head, self.fail_message

        def assert_last_log_with_retries(
            self, op: Callable, message: str, tries: int = 2, delay: float = 5.0
        ):
            times_tried = 0
            return_value = None
            while times_tried <= tries:
                result = op()

                # Only save the first return value.
                if return_value is None and result is not None:
                    return_value = result

                times_tried += 1
                if message in self.head:
                    return return_value

                time.sleep(delay)

                # Reset levels in case they got switched.
                self.set_levels()
                logger.set_level(LogLevel.INFO)
                caplog.set_level(LogLevel.WARNING)

            pytest.fail(self.fail_message)

    return ApeCaplog()


@pytest.fixture
def mock_home_directory(tmp_path):
    original_home = Path.home()
    Path.home = lambda: tmp_path  # type: ignore[method-assign]
    yield tmp_path
    Path.home = lambda: original_home  # type: ignore[method-assign]


class SubprocessRunner:
    """
    Same CLI commands are better tested using a python subprocess,
    such as `ape test` commands because duplicate pytest main methods
    do not run well together, or `ape plugins` commands, which may
    modify installed plugins.
    """

    def __init__(
        self, root_cmd: Optional[Sequence[str]] = None, data_folder: Optional[Path] = None
    ):
        self.root_cmd = root_cmd or []
        self.data_folder = data_folder

    def invoke(
        self,
        *subcommand: str,
        input=None,
        timeout: int = 40,
        env: Optional[dict] = None,
    ):
        subcommand = subcommand or ()
        cmd_ls = [*self.root_cmd, *subcommand]

        env = {**dict(os.environ), **(env or {})}
        if self.data_folder:
            env["APE_DATA_FOLDER"] = str(self.data_folder)

        completed_process = subprocess.run(
            cmd_ls, capture_output=True, env=env, input=input, text=True, timeout=timeout
        )
        result = SubprocessResult(completed_process)
        sys.stdin = sys.__stdin__
        return result


class ApeSubprocessRunner(SubprocessRunner):
    """
    Subprocess runner for Ape-specific commands.
    """

    def __init__(
        self,
        root_cmd: Optional[Union[str, Sequence[str]]] = None,
        data_folder: Optional[Path] = None,
    ):
        ape_path = Path(sys.executable).parent / "ape"

        root = root_cmd or ()
        if isinstance(root, str):
            root = (root,)

        super().__init__([str(ape_path), *root], data_folder=data_folder)
        self.project = None

    def invoke(self, *subcommand: str, input=None, timeout: int = 40, env: Optional[dict] = None):
        if self.project:
            try:
                here = os.getcwd()
            except Exception:
                here = None

            os.chdir(f"{self.project.path}")

        else:
            here = None

        result = super().invoke(*subcommand, input=input, timeout=timeout, env=env)
        if here:
            os.chdir(here)

        return result


class SubprocessResult:
    def __init__(self, completed_process: subprocess.CompletedProcess):
        self._completed_process = completed_process

    @property
    def exit_code(self) -> int:
        return self._completed_process.returncode

    @property
    def output(self) -> str:
        return self._completed_process.stdout or self._completed_process.stderr


CUSTOM_NETWORK_0 = "apenet"
CUSTOM_NETWORK_CHAIN_ID_0 = 944898498948934528628
CUSTOM_NETWORK_1 = "apenet1"
CUSTOM_NETWORK_CHAIN_ID_1 = 944898498948934528629
CUSTOM_BLOCK_TIME = 123


def _make_net(name: str, chain_id: int, **kwargs) -> dict:
    return {"name": name, "chain_id": chain_id, "ecosystem": "ethereum", **kwargs}


CUSTOM_NETWORKS_CONFIG = {
    "networks": {
        "custom": [
            _make_net(CUSTOM_NETWORK_0, CUSTOM_NETWORK_CHAIN_ID_0),
            _make_net(CUSTOM_NETWORK_1, CUSTOM_NETWORK_CHAIN_ID_1),
        ]
    }
}


@pytest.fixture(scope="session")
def custom_networks_config_dict():
    return CUSTOM_NETWORKS_CONFIG


@pytest.fixture(scope="session")
def custom_network_name_0():
    return CUSTOM_NETWORK_0


@pytest.fixture(scope="session")
def custom_network_name_1():
    return CUSTOM_NETWORK_1


@pytest.fixture(scope="session")
def custom_network_chain_id_0():
    return CUSTOM_NETWORK_CHAIN_ID_0


@pytest.fixture(scope="session")
def custom_network_chain_id_1():
    return CUSTOM_NETWORK_CHAIN_ID_1


@pytest.fixture
def custom_network(ethereum, project, custom_networks_config_dict):
    with project.temp_config(**custom_networks_config_dict):
        yield ethereum.apenet


@pytest.fixture
def config_wrapper(mocker):
    return ConfigWrapper(mocker.MagicMock())


@pytest.fixture
def gas_tracker(config_wrapper):
    return GasTracker(config_wrapper)


@pytest.fixture(scope="session")
def solidity_contract_type(get_contract_type) -> ContractType:
    return get_contract_type("SolidityContract")


@pytest.fixture(scope="session")
def get_contract_type():
    def fn(name: str) -> ContractType:
        content = (SHARED_CONTRACTS_FOLDER / f"{name}.json").read_text(encoding="utf8")
        return ContractType.model_validate_json(content)

    return fn


@pytest.fixture(scope="session")
def solidity_contract_container(solidity_contract_type) -> ContractContainer:
    return ContractContainer(contract_type=solidity_contract_type)


@pytest.fixture(scope="session")
def vyper_contract_type(get_contract_type) -> ContractType:
    return get_contract_type("VyperContract")


@pytest.fixture(scope="session")
def vyper_contract_container(vyper_contract_type) -> ContractContainer:
    return ContractContainer(contract_type=vyper_contract_type)


@pytest.fixture(scope="session")
def shared_contracts_folder():
    return SHARED_CONTRACTS_FOLDER


@pytest.fixture
def project_with_contracts(with_dependencies_project_path):
    return Project(with_dependencies_project_path)


@pytest.fixture
def geth_contract(geth_account, vyper_contract_container, geth_provider):
    return geth_account.deploy(vyper_contract_container, 0)
