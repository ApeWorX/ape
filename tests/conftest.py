import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from tempfile import mkdtemp
from typing import Dict, Optional

import pytest
import yaml
from click.testing import CliRunner

import ape
from ape.exceptions import APINotImplementedError, UnknownSnapshotError
from ape.managers.config import CONFIG_FILE_NAME

# NOTE: Ensure that we don't use local paths for these
ape.config.DATA_FOLDER = Path(mkdtemp()).resolve()
PROJECT_FOLDER = Path(mkdtemp()).resolve()
ape.config.PROJECT_FOLDER = PROJECT_FOLDER

# Needed to test tracing support in core `ape test` command.
pytest_plugins = ["pytester"]
geth_process_test = pytest.mark.xdist_group(name="geth-tests")
GETH_URI = "http://127.0.0.1:5550"


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
def data_folder(config):
    return config.DATA_FOLDER


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
    # NOTE: password is 'a'
    return {
        "address": "7e5f4552091a69125d5dfcb7b8c2659029395bdf",
        "crypto": {
            "cipher": "aes-128-ctr",
            "cipherparams": {"iv": "7bc492fb5dca4fe80fd47645b2aad0ff"},
            "ciphertext": "43beb65018a35c31494f642ec535315897634b021d7ec5bb8e0e2172387e2812",
            "kdf": "scrypt",
            "kdfparams": {
                "dklen": 32,
                "n": 262144,
                "r": 1,
                "p": 8,
                "salt": "4b127cb5ddbc0b3bd0cc0d2ef9a89bec",
            },
            "mac": "6a1d520975a031e11fc16cff610f5ae7476bcae4f2f598bc59ccffeae33b1caa",
        },
        "id": "ee424db9-da20-405d-bd75-e609d3e2b4ad",
        "version": 3,
    }


@pytest.fixture(scope="session")
def temp_accounts_path(config):
    path = Path(config.DATA_FOLDER) / "accounts"
    path.mkdir(exist_ok=True, parents=True)

    yield path

    if path.is_dir():
        shutil.rmtree(path)


@pytest.fixture(scope="session")
def runner():
    yield CliRunner()


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
def eth_tester_provider():
    if not ape.networks.active_provider or ape.networks.provider.name != "test":
        with ape.networks.ethereum.local.use_provider("test") as provider:
            yield provider
    else:
        yield ape.networks.provider


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
    if not networks.active_provider or networks.provider.name != "geth":
        with networks.ethereum.local.use_provider(
            "geth", provider_settings={"uri": GETH_URI}
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
        with tempfile.TemporaryDirectory() as temp_dir_str:
            temp_dir = Path(temp_dir_str)
            config._cached_configs = {}
            config_file = temp_dir / CONFIG_FILE_NAME
            config_file.touch()
            config_file.write_text(yaml.dump(data))
            config.load(force_reload=True)

            with config.using_project(temp_dir) as temp_project:
                yield temp_project

            config_file.unlink()
            config._cached_configs = {}

    return func


@pytest.fixture
def empty_data_folder():
    current_data_folder = ape.config.DATA_FOLDER
    ape.config.DATA_FOLDER = Path(mkdtemp()).resolve()
    yield
    ape.config.DATA_FOLDER = current_data_folder
