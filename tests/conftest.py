import json
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from tempfile import mkdtemp
from typing import Any, Callable, Dict, Optional, Sequence

import pytest
import yaml
from click.testing import CliRunner

import ape
from ape.exceptions import APINotImplementedError, UnknownSnapshotError
from ape.logging import LogLevel, logger
from ape.managers.config import CONFIG_FILE_NAME
from ape.types import AddressType
from ape.utils import DEFAULT_TEST_CHAIN_ID, ZERO_ADDRESS, create_tempdir
from ape.utils.basemodel import only_raise_attribute_error

# NOTE: Ensure that we don't use local paths for these
DATA_FOLDER = Path(mkdtemp()).resolve()
ape.config.DATA_FOLDER = DATA_FOLDER
ape.config.dependency_manager.DATA_FOLDER = DATA_FOLDER
PROJECT_FOLDER = Path(mkdtemp()).resolve()
ape.config.PROJECT_FOLDER = PROJECT_FOLDER

# Needed to test tracing support in core `ape test` command.
pytest_plugins = ["pytester"]
GETH_URI = "http://127.0.0.1:5550"
ALIAS = "__FUNCTIONAL_TESTS_ALIAS__"
geth_process_test = pytest.mark.xdist_group(name="geth-tests")
explorer_test = pytest.mark.xdist_group(name="explorer-tests")


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
def plugin_manager():
    return ape.networks.plugin_manager


@pytest.fixture(scope="session")
def accounts():
    return ape.accounts


@pytest.fixture(scope="session")
def compilers():
    return ape.compilers


@pytest.fixture(scope="session")
def networks():
    return ape.networks


@pytest.fixture(scope="session")
def chain():
    return ape.chain


@pytest.fixture(scope="session")
def project_folder():
    return PROJECT_FOLDER


@pytest.fixture(scope="session")
def test_accounts(accounts):
    return accounts.test_accounts


@pytest.fixture(scope="session")
def owner(test_accounts):
    return test_accounts[0]


@pytest.fixture(scope="session")
def sender(test_accounts):
    return test_accounts[1]


@pytest.fixture(scope="session")
def receiver(test_accounts):
    return test_accounts[2]


@pytest.fixture(scope="session")
def not_owner(test_accounts):
    return test_accounts[3]


@pytest.fixture(scope="session")
def helper(test_accounts):
    return test_accounts[4]


@pytest.fixture
def signer(test_accounts):
    return test_accounts[5]


@pytest.fixture
def geth_account(test_accounts):
    return test_accounts[6]


@pytest.fixture
def geth_second_account(test_accounts):
    return test_accounts[7]


@pytest.fixture
def project(config, project_folder):
    project_folder.mkdir(parents=True, exist_ok=True)
    with config.using_project(project_folder) as project:
        yield project


@pytest.fixture
def dependency_manager(project):
    return project.dependency_manager


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


@pytest.fixture(scope="session")
def temp_accounts_path(config):
    path = Path(config.DATA_FOLDER) / "accounts"
    path.mkdir(exist_ok=True, parents=True)

    yield path

    if path.is_dir():
        shutil.rmtree(path)


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
        or networks.provider.name != "geth"
        or not networks.provider.is_connected
        or getattr(networks.provider, "uri", "") != GETH_URI
    ):
        test_acct_100 = "0x63c7f11162dBFC374DC6f5C0B3Aa26C618846a85"
        with networks.ethereum.local.use_provider(
            "geth", provider_settings={"uri": GETH_URI, "extra_funded_accounts": [test_acct_100]}
        ) as provider:
            yield provider
    else:
        yield networks.provider


@contextmanager
def _isolation():
    if ape.networks.active_provider is None:
        raise AssertionError("Isolation should only be used with a connected provider.")

    init_network_name = ape.chain.provider.network.name
    init_provider_name = ape.chain.provider.name

    try:
        snapshot = ape.chain.snapshot()
    except APINotImplementedError:
        # Provider not used or connected in test.
        snapshot = None

    yield

    if (
        snapshot is None
        or ape.networks.active_provider is None
        or ape.chain.provider.network.name != init_network_name
        or ape.chain.provider.name != init_provider_name
    ):
        return

    try:
        ape.chain.restore(snapshot)
    except UnknownSnapshotError:
        # Assume snapshot removed for testing reasons
        # or the provider was not needed to be connected for the test.
        pass


@pytest.fixture(autouse=True)
def eth_tester_isolation(eth_tester_provider):
    with _isolation():
        yield


@pytest.fixture(scope="session")
def temp_config(config):
    @contextmanager
    def func(data: Optional[Dict] = None):
        data = data or {}
        with create_tempdir() as temp_dir:
            config._cached_configs = {}
            config_file = temp_dir / CONFIG_FILE_NAME
            config_file.touch()
            config_file.write_text(yaml.dump(data))

            with config.using_project(temp_dir) as temp_project:
                yield temp_project

            config_file.unlink()
            config._cached_configs = {}

    return func


@pytest.fixture
def empty_data_folder():
    current_data_folder = ape.config.DATA_FOLDER
    ape.config.DATA_FOLDER = Path(mkdtemp()).resolve()
    ape.config.dependency_manager.DATA_FOLDER = ape.config.DATA_FOLDER
    yield
    ape.config.DATA_FOLDER = current_data_folder
    ape.config.dependency_manager.DATA_FOLDER = ape.config.DATA_FOLDER


@pytest.fixture
def keyfile_account(owner, keyparams, temp_accounts_path, temp_keyfile_account_ctx):
    with temp_keyfile_account_ctx(temp_accounts_path, ALIAS, keyparams, owner) as account:
        # Ensure starts off locked.
        account.lock()
        yield account


@pytest.fixture
def temp_keyfile_account_ctx():
    @contextmanager
    def _temp_keyfile_account(base_path: Path, alias: str, keyparams, sender):
        test_keyfile_path = base_path / f"{alias}.json"

        if not test_keyfile_path.is_file():
            account = _make_keyfile_account(base_path, alias, keyparams, sender)
        else:
            account = ape.accounts.load(ALIAS)

        try:
            yield account
        finally:
            if test_keyfile_path.is_file():
                test_keyfile_path.unlink()

    return _temp_keyfile_account


def _make_keyfile_account(base_path: Path, alias: str, params: Dict, funder):
    test_keyfile_path = base_path / f"{alias}.json"

    if test_keyfile_path.is_file():
        # Corrupted from a previous test
        test_keyfile_path.unlink()

    test_keyfile_path.write_text(json.dumps(params))

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

                    def test_skip_from_compiler():
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
            self.messages_at_start = list(caplog.messages)
            self.set_levels(caplog_level=caplog_level)

        @only_raise_attribute_error
        def __getattr__(self, name: str) -> Any:
            return getattr(caplog, name)

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

        @classmethod
        def set_levels(cls, caplog_level: LogLevel = LogLevel.WARNING):
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

    def __init__(self, root_cmd: Optional[Sequence[str]] = None):
        self.root_cmd = root_cmd or []

    def invoke(self, subcommand: Optional[Sequence[str]] = None):
        subcommand = subcommand or []
        cmd_ls = [*self.root_cmd, *subcommand]
        completed_process = subprocess.run(cmd_ls, capture_output=True, text=True)
        return SubprocessResult(completed_process)


class ApeSubprocessRunner(SubprocessRunner):
    """
    Subprocess runner for Ape-specific commands.
    """

    def __init__(self, root_cmd: Optional[Sequence[str]] = None):
        ape_path = Path(sys.executable).parent / "ape"
        super().__init__([str(ape_path), *(root_cmd or [])])


class SubprocessResult:
    def __init__(self, completed_process: subprocess.CompletedProcess):
        self._completed_process = completed_process

    @property
    def exit_code(self) -> int:
        return self._completed_process.returncode

    @property
    def output(self) -> str:
        return self._completed_process.stdout


CUSTOM_NETWORK_0 = "apenet"
CUSTOM_NETWORK_CHAIN_ID_0 = 944898498948934528628
CUSTOM_NETWORK_1 = "apenet1"
CUSTOM_NETWORK_CHAIN_ID_1 = 944898498948934528629
CUSTOM_BLOCK_TIME = 123


def _make_net(name: str, chain_id: int, **kwargs) -> Dict:
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
def custom_networks_config(temp_config, custom_networks_config_dict):
    with temp_config(custom_networks_config_dict):
        yield custom_networks_config_dict


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
def custom_network(ethereum, custom_networks_config):
    return ethereum.apenet
