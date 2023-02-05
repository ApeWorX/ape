import json
import threading
import time
from contextlib import contextmanager
from distutils.dir_util import copy_tree
from pathlib import Path
from typing import Dict, Optional

import pytest
from ethpm_types import ContractType
from hexbytes import HexBytes

import ape
from ape.api import EcosystemAPI, NetworkAPI, TransactionAPI
from ape.api.networks import LOCAL_NETWORK_NAME
from ape.contracts import ContractContainer, ContractInstance
from ape.exceptions import ChainError, ContractLogicError
from ape.logging import LogLevel
from ape.logging import logger as _logger
from ape.types import AddressType, ContractLog

PROJECT_PATH = Path(__file__).parent
CONTRACTS_FOLDER = PROJECT_PATH / "data" / "contracts" / "ethereum" / "local"


def _get_raw_contract(name: str) -> str:
    return (CONTRACTS_FOLDER / f"{name}.json").read_text()


ALIAS = "__FUNCTIONAL_TESTS_ALIAS__"
ALIAS_2 = "__FUNCTIONAL_TESTS_ALIAS_2__"
RAW_SOLIDITY_CONTRACT_TYPE = _get_raw_contract("solidity_contract")
RAW_VYPER_CONTRACT_TYPE = _get_raw_contract("vyper_contract")
RAW_REVERTS_CONTRACT_TYPE = _get_raw_contract("reverts_contract")
TEST_ADDRESS = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
BASE_PROJECTS_DIRECTORY = (Path(__file__).parent / "data" / "projects").absolute()
PROJECT_WITH_LONG_CONTRACTS_FOLDER = BASE_PROJECTS_DIRECTORY / "LongContractsFolder"
DS_NOTE_TEST_CONTRACT_TYPE = _get_raw_contract("ds_note_test")
APE_PROJECT_FOLDER = BASE_PROJECTS_DIRECTORY / "ApeProject"
BASE_SOURCES_DIRECTORY = (Path(__file__).parent / "data/sources").absolute()


class _ContractLogicError(ContractLogicError):
    pass


@pytest.hookimpl(trylast=True, hookwrapper=True)
def pytest_collection_finish(session):
    with ape.networks.parse_network_choice("::test"):
        # Sets the active provider
        yield


@pytest.fixture
def mock_network_api(mocker):
    mock = mocker.MagicMock(spec=NetworkAPI)
    mock_ecosystem = mocker.MagicMock(spec=EcosystemAPI)
    mock_ecosystem.virtual_machine_error_class = _ContractLogicError
    mock.ecosystem = mock_ecosystem
    return mock


@pytest.fixture
def mock_web3(mocker):
    return mocker.MagicMock()


@pytest.fixture
def mock_transaction(mocker):
    return mocker.MagicMock(spec=TransactionAPI)


@pytest.fixture(scope="session")
def test_accounts(accounts):
    return accounts.test_accounts


@pytest.fixture
def project_path():
    return PROJECT_PATH


@pytest.fixture
def contracts_folder():
    return CONTRACTS_FOLDER


@pytest.fixture(scope="session")
def sender(test_accounts):
    return test_accounts[0]


@pytest.fixture(scope="session")
def receiver(test_accounts):
    return test_accounts[1]


@pytest.fixture(scope="session")
def owner(test_accounts):
    return test_accounts[2]


@pytest.fixture
def address():
    return TEST_ADDRESS


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


@pytest.fixture
def keyfile_account(sender, keyparams, temp_accounts_path):
    with _temp_keyfile_account(temp_accounts_path, ALIAS, keyparams, sender) as account:
        yield account


@pytest.fixture
def second_keyfile_account(sender, keyparams, temp_accounts_path):
    with _temp_keyfile_account(temp_accounts_path, ALIAS_2, keyparams, sender) as account:
        yield account


def _make_keyfile_account(base_path: Path, alias: str, params: Dict, funder):
    test_keyfile_path = base_path / f"{alias}.json"

    if test_keyfile_path.is_file():
        # Corrupted from a previous test
        test_keyfile_path.unlink()

    test_keyfile_path.write_text(json.dumps(params))

    acct = ape.accounts.load(alias)
    funder.transfer(acct, "25 ETH")  # Auto-fund this account
    return acct


@pytest.fixture
def solidity_contract_type() -> ContractType:
    return ContractType.parse_raw(RAW_SOLIDITY_CONTRACT_TYPE)


@pytest.fixture
def solidity_contract_container(solidity_contract_type) -> ContractContainer:
    return ContractContainer(contract_type=solidity_contract_type)


@pytest.fixture
def solidity_contract_instance(
    owner, solidity_contract_container, networks_connected_to_tester
) -> ContractInstance:
    return owner.deploy(solidity_contract_container, 0)


@pytest.fixture
def vyper_contract_type() -> ContractType:
    return ContractType.parse_raw(RAW_VYPER_CONTRACT_TYPE)


@pytest.fixture
def vyper_contract_container(vyper_contract_type) -> ContractContainer:
    return ContractContainer(contract_type=vyper_contract_type)


@pytest.fixture
def vyper_contract_instance(
    owner, vyper_contract_container, networks_connected_to_tester
) -> ContractInstance:
    return owner.deploy(vyper_contract_container, 0, required_confirmations=0)


@pytest.fixture
def reverts_contract_type() -> ContractType:
    result = ContractType.parse_raw(RAW_REVERTS_CONTRACT_TYPE)
    result.dev_messages = {
        6: "dev: one",
        7: "dev: error",
        9: "dev: such modifiable, wow",
        12: "dev: great job",
    }
    return result


@pytest.fixture
def reverts_contract_container(reverts_contract_type) -> ContractContainer:
    return ContractContainer(contract_type=reverts_contract_type)


@pytest.fixture
def reverts_contract_instance(
    owner, reverts_contract_container, networks_connected_to_tester, geth_provider
) -> ContractInstance:
    _ = geth_provider  # Must use geth, as it supports traces
    return owner.deploy(reverts_contract_container, required_confirmations=0)


@pytest.fixture(params=("solidity", "vyper"))
def contract_container(
    request, solidity_contract_container, vyper_contract_container, networks_connected_to_tester
):
    return solidity_contract_container if request.param == "solidity" else vyper_contract_container


@pytest.fixture(params=("solidity", "vyper"))
def contract_instance(
    eth_tester_provider, request, solidity_contract_instance, vyper_contract_instance
):
    return solidity_contract_instance if request.param == "solidity" else vyper_contract_instance


@pytest.fixture
def ds_note_test_contract(eth_tester_provider, vyper_contract_type, owner):
    contract_type = ContractType.parse_raw(DS_NOTE_TEST_CONTRACT_TYPE)
    contract_container = ContractContainer(contract_type=contract_type)
    return contract_container.deploy(sender=owner)


@pytest.fixture
def project_with_contract(temp_config):
    with temp_config() as project:
        copy_tree(str(APE_PROJECT_FOLDER), str(project.path))
        yield project


@pytest.fixture
def project_with_source_files_contract(temp_config):
    bases_source_dir = BASE_SOURCES_DIRECTORY
    project_source_dir = APE_PROJECT_FOLDER

    with temp_config() as project:
        copy_tree(str(project_source_dir), str(project.path))
        copy_tree(str(bases_source_dir), f"{project.path}/contracts/")
        yield project


@pytest.fixture
def clean_contracts_cache(chain):
    original_cached_contracts = chain.contracts._local_contract_types
    chain.contracts._local_contract_types = {}
    yield
    chain.contracts._local_contract_types = original_cached_contracts


@pytest.fixture
def project_with_dependency_config(temp_config):
    dependencies_config = {
        "dependencies": [
            {
                "local": str(PROJECT_WITH_LONG_CONTRACTS_FOLDER),
                "name": "testdependency",
                "contracts_folder": "source/v0.1",
            }
        ]
    }
    with temp_config(dependencies_config) as project:
        yield project


@pytest.fixture
def base_projects_directory():
    return BASE_PROJECTS_DIRECTORY


@pytest.fixture
def mainnet_contract(chain):
    def contract_getter(address):
        path = (
            Path(__file__).parent
            / "data"
            / "contracts"
            / "ethereum"
            / "mainnet"
            / f"{address}.json"
        )
        contract = ContractType.parse_file(path)
        chain.contracts._local_contract_types[address] = contract
        return contract

    return contract_getter


@pytest.fixture
def ds_note():
    return {
        "address": "0x35D1b3F3D7966A1DFe207aa4514C12a259A0492B",
        "topics": [
            HexBytes("0x7608870300000000000000000000000000000000000000000000000000000000"),
            HexBytes("0x5946492d41000000000000000000000000000000000000000000000000000000"),
            HexBytes("0x0000000000000000000000000abb839063ef747c8432b2acc60bf8f70ec09a45"),
            HexBytes("0x0000000000000000000000000abb839063ef747c8432b2acc60bf8f70ec09a45"),
        ],
        "data": "0x000000000000000000000000000000000000000000000000000000000000002000000000000000000000000000000000000000000000000000000000000000e0760887035946492d410000000000000000000000000000000000000000000000000000000000000000000000000000000abb839063ef747c8432b2acc60bf8f70ec09a450000000000000000000000000abb839063ef747c8432b2acc60bf8f70ec09a450000000000000000000000000abb839063ef747c8432b2acc60bf8f70ec09a450000000000000000000000000000000000000000000000000000000000000000fffffffffffffffffffffffffffffffffffffffffffa050e82a57b7fc6b6020c00000000000000000000000000000000000000000000000000000000",  # noqa: E501
        "blockNumber": 14623434,
        "transactionHash": HexBytes(
            "0xa322a9fd0e627e22bfe1b0877cca1d1f2e697d076007231d0b7a366d1a0fdd51"
        ),
        "transactionIndex": 333,
        "blockHash": HexBytes("0x0fd77b0af3fa471aa040a02d4fcd1ec0a35122a4166d0bb7c31354e23823de49"),
        "logIndex": 376,
        "removed": False,
    }


@pytest.fixture
def chain_that_mined_5(chain):
    chain.mine(5)
    return chain


class PollDaemonThread(threading.Thread):
    def __init__(self, name, poller, handler, stop_condition, *args, **kwargs):
        kwargs_dict = dict(**kwargs)
        kwargs_dict["name"] = f"ape_poll_{name}"
        super().__init__(*args, **kwargs_dict)
        self._poller = poller
        self._handler = handler
        self._do_stop = stop_condition
        self._exception = None
        self._max_iterations = 100

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        self.stop()

    def run(self):
        try:
            self._run_until_stop(timeout_iterations=self._max_iterations)
        except Exception as err:
            self._exception = err

    def stop(self):
        time.sleep(1)
        self.join()

        # Attempt to wait for stop condition
        if not self._do_stop():
            self._run_until_stop(timeout_iterations=10)

    def join(self, timeout=None):
        super().join(timeout=timeout)
        if self._exception and not self._do_stop():
            # Only raise if error-ed before hitting stop condition
            raise self._exception

    def _run_until_stop(self, timeout_iterations: Optional[int] = None):
        iterations = 0
        while True:
            if self._do_stop():
                return

            try:
                self._handler(next(self._poller))
            except ChainError:
                # Check if can stop once more before exiting
                if self._do_stop():
                    return

                raise  # The timeout ChainError

            time.sleep(1)
            if timeout_iterations is None:
                continue

            elif iterations >= timeout_iterations:
                return

            iterations += 1


@pytest.fixture
def PollDaemon():
    return PollDaemonThread


@pytest.fixture
def assert_log_values(contract_instance):
    def _assert_log_values(
        log: ContractLog,
        number: int,
        previous_number: Optional[int] = None,
        address: Optional[AddressType] = None,
    ):
        assert log.contract_address == address or contract_instance.address
        assert isinstance(log.b, HexBytes)
        expected_previous_number = number - 1 if previous_number is None else previous_number
        assert log.prevNum == expected_previous_number, "Event param 'prevNum' has unexpected value"
        assert log.newNum == number, "Event param 'newNum' has unexpected value"
        assert log.dynData == "Dynamic"
        assert log.dynIndexed == HexBytes(
            "0x9f3d45ac20ccf04b45028b8080bb191eab93e29f7898ed43acf480dd80bba94d"
        )

    return _assert_log_values


@pytest.fixture
def remove_disk_writes_deployments(chain):
    if chain.contracts._deployments_mapping_cache.is_file():
        chain.contracts._deployments_mapping_cache.unlink()

    yield

    if chain.contracts._deployments_mapping_cache.is_file():
        chain.contracts._deployments_mapping_cache.unlink()


@pytest.fixture
def logger():
    return _logger


@pytest.fixture
def use_debug(logger):
    initial_level = logger.level
    logger.set_level(LogLevel.DEBUG)
    yield
    logger.set_level(initial_level)


@pytest.fixture
def dummy_live_network(chain):
    chain.provider.network.name = "goerli"
    yield chain.provider.network
    chain.provider.network.name = LOCAL_NETWORK_NAME


@pytest.fixture
def proxy_contract_container():
    contract_type = ContractType.parse_raw(_get_raw_contract("proxy"))
    return ContractContainer(contract_type)


@pytest.fixture
def calldata():
    return HexBytes(
        "0x3fb5c1cb00000000000000000000000000000000000000000000000000000000000000de"
    )  # setNumber(222)


@pytest.fixture
def calldata_with_address():
    return HexBytes(
        "0x9e6b154b00000000000000000000000000000000000000000000000000000000000000de"
        "000000000000000000000000f7f78379391c5df2db5b66616d18ff92edb82022"
    )  # setNumber(222, 0xf7f78379391c5df2db5b66616d18ff92edb82022)


@pytest.fixture
def unique_calldata():
    return HexBytes(
        "0xacab48d8"
        "0000000000000000000000000000000000000000000000000000000000000000"
        "0000000000000000000000000000000000000000000000000000000000000001"
        "0000000000000000000000000000000000000000000000000000000000000002"
        "0000000000000000000000000000000000000000000000000000000000000003"
        "0000000000000000000000000000000000000000000000000000000000000004"
        "0000000000000000000000000000000000000000000000000000000000000005"
        "0000000000000000000000000000000000000000000000000000000000000006"
        "0000000000000000000000000000000000000000000000000000000000000007"
        "0000000000000000000000000000000000000000000000000000000000000008"
        "0000000000000000000000000000000000000000000000000000000000000009"
    )  # functionWithUniqueArguments(0, 1, 2, 3, 4, 5, 6, 7, 8, 9)


@pytest.fixture
def contract_for_trace(owner, geth_provider):
    def get_contract_type(suffix: str) -> ContractType:
        return ContractType.parse_file(CONTRACTS_FOLDER / f"contract_{suffix}.json")

    contract_c = owner.deploy(ContractContainer(get_contract_type("c")))
    contract_b = owner.deploy(ContractContainer(get_contract_type("b")), contract_c.address)
    contract_a = owner.deploy(
        ContractContainer(get_contract_type("a")), contract_b.address, contract_c.address
    )

    return contract_a
