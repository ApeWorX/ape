import json
from pathlib import Path
from tempfile import mkdtemp

import pytest
from eth_account import Account

import ape

# NOTE: Ensure that we don't use local paths for these
ape.config.DATA_FOLDER = Path(mkdtemp()).resolve()
ape.config.PROJECT_FOLDER = Path(mkdtemp()).resolve()

ALIAS = "test"
PRIVATE_KEY = "0000000000000000000000000000000000000000000000000000000000000001"
ADDRESS = "7e5f4552091a69125d5dfcb7b8c2659029395bdf"


@pytest.fixture(scope="session")
def config():
    yield ape.config


@pytest.fixture(scope="session")
def data_folder(config):
    yield config.DATA_FOLDER


@pytest.fixture(scope="session")
def plugin_manager():
    yield ape.plugin_manager


@pytest.fixture(scope="session")
def accounts():
    yield ape.accounts


@pytest.fixture(scope="session")
def compilers():
    yield ape.compilers


@pytest.fixture(scope="session")
def networks():
    yield ape.networks


@pytest.fixture(scope="session")
def chain():
    yield ape.chain


@pytest.fixture(scope="session")
def project_folder(config):
    yield config.PROJECT_FOLDER


@pytest.fixture(scope="session")
def project(config):
    yield ape.Project(config.PROJECT_FOLDER)


@pytest.fixture
def keyparams():
    # NOTE: password is 'a'
    return {
        "address": ADDRESS,
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


@pytest.fixture(autouse=True)
def temp_keyfile_path(config):
    temp_accounts_dir = Path(config.DATA_FOLDER) / "accounts"
    temp_accounts_dir.mkdir(exist_ok=True, parents=True)
    test_keyfile_path = temp_accounts_dir / f"{ALIAS}.json"

    if test_keyfile_path.exists():
        # Corrupted from a previous test
        test_keyfile_path.unlink()

    return test_keyfile_path


@pytest.fixture
def temp_keyfile(temp_keyfile_path, keyparams):
    temp_keyfile_path.write_text(json.dumps(keyparams))

    yield temp_keyfile_path

    if temp_keyfile_path.exists():
        temp_keyfile_path.unlink()


@pytest.fixture
def temp_eth_account(temp_keyfile):
    return Account.from_key(bytes.fromhex(PRIVATE_KEY))


@pytest.fixture
def temp_ape_account(temp_keyfile, accounts):
    return accounts[ADDRESS]
