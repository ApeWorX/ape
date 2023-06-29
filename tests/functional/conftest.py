import threading
import time
from distutils.dir_util import copy_tree
from pathlib import Path
from typing import Optional

import pytest
from ethpm_types import ContractType, HexBytes

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


@pytest.fixture
def get_contract_type():
    def fn(name: str) -> ContractType:
        return ContractType.parse_file(CONTRACTS_FOLDER / f"{name}.json")

    return fn


ALIAS_2 = "__FUNCTIONAL_TESTS_ALIAS_2__"
TEST_ADDRESS = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
BASE_PROJECTS_DIRECTORY = (Path(__file__).parent / "data" / "projects").absolute()
PROJECT_WITH_LONG_CONTRACTS_FOLDER = BASE_PROJECTS_DIRECTORY / "LongContractsFolder"
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


@pytest.fixture
def project_path():
    return PROJECT_PATH


@pytest.fixture
def contracts_folder():
    return CONTRACTS_FOLDER


@pytest.fixture(scope="session")
def receiver(test_accounts):
    return test_accounts[1]


@pytest.fixture(scope="session")
def owner(test_accounts):
    return test_accounts[2]


@pytest.fixture(scope="session")
def not_owner(test_accounts):
    return test_accounts[7]


@pytest.fixture
def address():
    return TEST_ADDRESS


@pytest.fixture
def second_keyfile_account(sender, keyparams, temp_accounts_path, temp_keyfile_account_ctx):
    with temp_keyfile_account_ctx(temp_accounts_path, ALIAS_2, keyparams, sender) as account:
        yield account


@pytest.fixture
def solidity_contract_type(get_contract_type) -> ContractType:
    return get_contract_type("solidity_contract")


@pytest.fixture
def solidity_contract_container(solidity_contract_type) -> ContractContainer:
    return ContractContainer(contract_type=solidity_contract_type)


@pytest.fixture
def solidity_contract_instance(
    owner, solidity_contract_container, networks_connected_to_tester
) -> ContractInstance:
    return owner.deploy(solidity_contract_container, 0)


@pytest.fixture
def vyper_contract_type(get_contract_type) -> ContractType:
    return get_contract_type("vyper_contract")


@pytest.fixture
def solidity_fallback_contract_type(get_contract_type) -> ContractType:
    return get_contract_type("sol_fallback_and_receive")


@pytest.fixture
def vyper_fallback_contract_type(get_contract_type) -> ContractType:
    return get_contract_type("vy_default")


@pytest.fixture
def vyper_contract_container(vyper_contract_type) -> ContractContainer:
    return ContractContainer(contract_type=vyper_contract_type)


@pytest.fixture
def solidity_fallback_container(solidity_fallback_contract_type) -> ContractContainer:
    return ContractContainer(contract_type=solidity_fallback_contract_type)


@pytest.fixture
def vyper_fallback_container(vyper_fallback_contract_type) -> ContractContainer:
    return ContractContainer(contract_type=vyper_fallback_contract_type)


@pytest.fixture
def vyper_math_dev_check(get_contract_type) -> ContractContainer:
    return ContractContainer(contract_type=get_contract_type("vyper_math_dev_checks"))


@pytest.fixture
def vyper_contract_instance(
    owner, vyper_contract_container, networks_connected_to_tester
) -> ContractInstance:
    return owner.deploy(vyper_contract_container, 0, required_confirmations=0)


@pytest.fixture
def solidity_fallback_contract(owner, solidity_fallback_container):
    return owner.deploy(solidity_fallback_container)


@pytest.fixture
def vyper_fallback_contract(owner, vyper_fallback_container):
    return owner.deploy(vyper_fallback_container)


@pytest.fixture
def reverts_contract_type(get_contract_type) -> ContractType:
    return get_contract_type("reverts_contract")


@pytest.fixture
def sub_reverts_contract_type(get_contract_type) -> ContractType:
    return get_contract_type("sub_reverts_contract")


@pytest.fixture
def reverts_contract_container(reverts_contract_type) -> ContractContainer:
    return ContractContainer(contract_type=reverts_contract_type)


@pytest.fixture
def sub_reverts_contract_container(sub_reverts_contract_type) -> ContractContainer:
    return ContractContainer(contract_type=sub_reverts_contract_type)


@pytest.fixture
def reverts_contract_instance(
    owner, reverts_contract_container, sub_reverts_contract_instance, geth_provider
) -> ContractInstance:
    return owner.deploy(
        reverts_contract_container, sub_reverts_contract_instance, required_confirmations=0
    )


@pytest.fixture
def sub_reverts_contract_instance(owner, sub_reverts_contract_container, geth_provider):
    return owner.deploy(sub_reverts_contract_container, required_confirmations=0)


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


@pytest.fixture(params=("solidity", "vyper"))
def fallback_contract(
    eth_tester_provider, request, solidity_fallback_contract, vyper_fallback_contract
):
    return solidity_fallback_contract if request.param == "solidity" else vyper_fallback_contract


@pytest.fixture
def ds_note_test_contract(eth_tester_provider, vyper_contract_type, owner, get_contract_type):
    contract_type = get_contract_type("ds_note_test")
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
def proxy_contract_container(get_contract_type):
    return ContractContainer(get_contract_type("proxy"))


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
def leaf_contract_geth(geth_provider, owner, get_contract_type):
    """
    The last contract called by `contract_with_call_depth`.
    """
    ct = get_contract_type("contract_c")
    return owner.deploy(ContractContainer(ct))


@pytest.fixture
def leaf_contract(eth_tester_provider, owner, get_contract_type):
    ct = get_contract_type("contract_c")
    return owner.deploy(ContractContainer(ct))


@pytest.fixture
def middle_contract_geth(geth_provider, owner, leaf_contract_geth, get_contract_type):
    """
    The middle contract called by `contract_with_call_depth`.
    """
    ct = get_contract_type("contract_b")
    return owner.deploy(ContractContainer(ct), leaf_contract_geth)


@pytest.fixture
def middle_contract(eth_tester_provider, owner, get_contract_type, leaf_contract):
    ct = get_contract_type("contract_b")
    return owner.deploy(ContractContainer(ct), leaf_contract)


@pytest.fixture
def contract_with_call_depth_geth(
    owner, geth_provider, get_contract_type, leaf_contract_geth, middle_contract_geth
):
    """
    This contract has methods that make calls to other local contracts
    and is used for any testing that requires nested calls, such as
    call trees or event-name clashes.
    """
    contract = ContractContainer(get_contract_type("contract_a"))
    return owner.deploy(contract, middle_contract_geth, leaf_contract_geth)


@pytest.fixture
def contract_with_call_depth(
    owner, eth_tester_provider, get_contract_type, leaf_contract, middle_contract
):
    contract = ContractContainer(get_contract_type("contract_a"))
    return owner.deploy(contract, middle_contract, leaf_contract)


@pytest.fixture
def error_contract_container(get_contract_type):
    ct = get_contract_type("has_error")
    return ContractContainer(ct)


@pytest.fixture
def error_contract(owner, error_contract_container, eth_tester_provider):
    _ = eth_tester_provider  # Ensure uses eth tester
    return owner.deploy(error_contract_container, 1)


@pytest.fixture
def error_contract_geth(owner, error_contract_container, geth_provider):
    _ = geth_provider  # Ensure uses geth
    return owner.deploy(error_contract_container, 1)


@pytest.fixture
def vyper_factory(owner, get_contract_type):
    return owner.deploy(ContractContainer(get_contract_type("vyper_factory")))


@pytest.fixture
def vyper_blueprint(owner, vyper_contract_container):
    receipt = owner.declare(vyper_contract_container)
    return receipt.contract_address


@pytest.fixture
def geth_vyper_contract(owner, vyper_contract_container, geth_provider):
    return owner.deploy(vyper_contract_container, 0)
