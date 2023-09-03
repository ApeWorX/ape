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


@pytest.fixture(scope="session")
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


@pytest.fixture(scope="session")
def project_path():
    return PROJECT_PATH


@pytest.fixture(scope="session")
def contracts_folder():
    return CONTRACTS_FOLDER


@pytest.fixture(scope="session")
def address():
    return TEST_ADDRESS


@pytest.fixture
def second_keyfile_account(sender, keyparams, temp_accounts_path, temp_keyfile_account_ctx):
    with temp_keyfile_account_ctx(temp_accounts_path, ALIAS_2, keyparams, sender) as account:
        yield account


@pytest.fixture(scope="session")
def solidity_contract_type(get_contract_type) -> ContractType:
    return get_contract_type("solidity_contract")


@pytest.fixture(scope="session")
def solidity_contract_container(solidity_contract_type) -> ContractContainer:
    return ContractContainer(contract_type=solidity_contract_type)


@pytest.fixture
def solidity_contract_instance(
    owner, solidity_contract_container, networks_connected_to_tester
) -> ContractInstance:
    return owner.deploy(solidity_contract_container, 0)


@pytest.fixture(scope="session")
def vyper_contract_type(get_contract_type) -> ContractType:
    return get_contract_type("vyper_contract")


@pytest.fixture(scope="session")
def solidity_fallback_contract_type(get_contract_type) -> ContractType:
    return get_contract_type("sol_fallback_and_receive")


@pytest.fixture(scope="session")
def vyper_fallback_contract_type(get_contract_type) -> ContractType:
    return get_contract_type("vy_default")


@pytest.fixture(scope="session")
def vyper_contract_container(vyper_contract_type) -> ContractContainer:
    return ContractContainer(contract_type=vyper_contract_type)


@pytest.fixture(scope="session")
def solidity_fallback_container(solidity_fallback_contract_type) -> ContractContainer:
    return ContractContainer(contract_type=solidity_fallback_contract_type)


@pytest.fixture(scope="session")
def vyper_fallback_container(vyper_fallback_contract_type) -> ContractContainer:
    return ContractContainer(contract_type=vyper_fallback_contract_type)


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


@pytest.fixture(scope="session")
def reverts_contract_type(get_contract_type) -> ContractType:
    return get_contract_type("reverts_contract")


@pytest.fixture(scope="session")
def sub_reverts_contract_type(get_contract_type) -> ContractType:
    return get_contract_type("sub_reverts")


@pytest.fixture(scope="session")
def reverts_contract_container(reverts_contract_type) -> ContractContainer:
    return ContractContainer(contract_type=reverts_contract_type)


@pytest.fixture(scope="session")
def sub_reverts_contract_container(sub_reverts_contract_type) -> ContractContainer:
    return ContractContainer(contract_type=sub_reverts_contract_type)


@pytest.fixture
def reverts_contract_instance(
    owner, reverts_contract_container, sub_reverts_contract_instance, eth_tester_provider
) -> ContractInstance:
    return owner.deploy(
        reverts_contract_container, sub_reverts_contract_instance, required_confirmations=0
    )


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


@pytest.fixture(scope="session")
def base_projects_directory():
    return BASE_PROJECTS_DIRECTORY


@pytest.fixture(scope="session")
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


@pytest.fixture(scope="session")
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


@pytest.fixture(scope="session")
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


@pytest.fixture(scope="session")
def proxy_contract_container(get_contract_type):
    return ContractContainer(get_contract_type("proxy"))


@pytest.fixture(scope="session")
def calldata():
    return HexBytes(
        "0x3fb5c1cb00000000000000000000000000000000000000000000000000000000000000de"
    )  # setNumber(222)


@pytest.fixture(scope="session")
def calldata_with_address():
    return HexBytes(
        "0x9e6b154b00000000000000000000000000000000000000000000000000000000000000de"
        "000000000000000000000000f7f78379391c5df2db5b66616d18ff92edb82022"
    )  # setNumber(222, 0xf7f78379391c5df2db5b66616d18ff92edb82022)


@pytest.fixture(scope="session")
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
def leaf_contract(eth_tester_provider, owner, get_contract_type):
    ct = get_contract_type("contract_c")
    return owner.deploy(ContractContainer(ct))


@pytest.fixture
def middle_contract(eth_tester_provider, owner, get_contract_type, leaf_contract):
    ct = get_contract_type("contract_b")
    return owner.deploy(ContractContainer(ct), leaf_contract)


@pytest.fixture
def contract_with_call_depth(
    owner, eth_tester_provider, get_contract_type, leaf_contract, middle_contract
):
    contract = ContractContainer(get_contract_type("contract_a"))
    return owner.deploy(contract, middle_contract, leaf_contract)


@pytest.fixture
def sub_reverts_contract_instance(owner, sub_reverts_contract_container, eth_tester_provider):
    return owner.deploy(sub_reverts_contract_container, required_confirmations=0)


@pytest.fixture(scope="session")
def error_contract_container(get_contract_type):
    ct = get_contract_type("has_error")
    return ContractContainer(ct)


@pytest.fixture
def error_contract(owner, error_contract_container, eth_tester_provider):
    _ = eth_tester_provider  # Ensure uses eth tester
    return owner.deploy(error_contract_container, 1)


@pytest.fixture
def vyper_factory(owner, get_contract_type):
    return owner.deploy(ContractContainer(get_contract_type("vyper_factory")))


@pytest.fixture
def vyper_blueprint(owner, vyper_contract_container):
    receipt = owner.declare(vyper_contract_container)
    return receipt.contract_address


@pytest.fixture
def solidity_contract_instance_abi():
    return '[{"inputs":[{"internalType":"uint256","name":"num" \
    ,"type":"uint256"}],"stateMutability":"nonpayable" \
    ,"type":"constructor"},{"anonymous":false,"inputs":[{"indexed":true \
    ,"internalType":"address","name":"newAddress","type":"address"}] \
    ,"name":"AddressChange","type":"event"},{"anonymous":false \
    ,"inputs":[{"indexed":true,"internalType":"uint256" \
    ,"name":"bar","type":"uint256"}],"name":"BarHappened" \
    ,"type":"event"},{"anonymous":false,"inputs":[{"indexed":true \
    ,"internalType":"uint256","name":"foo","type":"uint256"}] \
    ,"name":"FooHappened","type":"event"},{"anonymous":false \
    ,"inputs":[{"indexed":false,"internalType":"bytes32" \
    ,"name":"b","type":"bytes32"},{"indexed":false,"internalType":"uint256" \
    ,"name":"prevNum","type":"uint256"},{"indexed":false \
    ,"internalType":"string","name":"dynData","type":"string"} \
    ,{"indexed":true,"internalType":"uint256","name":"newNum" \
    ,"type":"uint256"},{"indexed":true,"internalType":"string" \
    ,"name":"dynIndexed","type":"string"}],"name":"NumberChange" \
    ,"type":"event"},{"inputs":[{"internalType":"address" \
    ,"name":"","type":"address"}],"name":"balances","outputs":[{"internalType":"uint256" \
    ,"name":"","type":"uint256"}],"stateMutability":"view" \
    ,"type":"function"},{"inputs":[],"name":"fooAndBar" \
    ,"outputs":[],"stateMutability":"nonpayable","type":"function"} \
    ,{"inputs":[{"internalType":"uint256","name":"a0","type":"uint256"} \
    ,{"internalType":"uint256","name":"a1","type":"uint256"} \
    ,{"internalType":"uint256","name":"a2","type":"uint256"} \
    ,{"internalType":"uint256","name":"a3","type":"uint256"} \
    ,{"internalType":"uint256","name":"a4","type":"uint256"} \
    ,{"internalType":"uint256","name":"a5","type":"uint256"} \
    ,{"internalType":"uint256","name":"a6","type":"uint256"} \
    ,{"internalType":"uint256","name":"a7","type":"uint256"} \
    ,{"internalType":"uint256","name":"a8","type":"uint256"} \
    ,{"internalType":"uint256","name":"a9","type":"uint256"}] \
    ,"name":"functionWithUniqueAmountOfArguments","outputs":[] \
    ,"stateMutability":"view","type":"function"},{"inputs":[] \
    ,"name":"getAddressArray","outputs":[{"internalType":"address[2]" \
    ,"name":"","type":"address[2]"}],"stateMutability":"view" \
    ,"type":"function"},{"inputs":[],"name":"getArrayWithBiggerSize" \
    ,"outputs":[{"internalType":"uint256[20]","name":"" \
    ,"type":"uint256[20]"}],"stateMutability":"pure","type":"function"} \
    ,{"inputs":[],"name":"getDynamicStructArray","outputs":\
    [{"components":[{"components":[{"internalType":"address" \
    ,"name":"a","type":"address"},{"internalType":"bytes32" \
    ,"name":"b","type":"bytes32"}],"internalType":"struct \
    TestContractSol.MyStruct","name":"t","type":"tuple"} \
    ,{"internalType":"uint256","name":"foo","type":"uint256"}] \
    ,"internalType":"struct TestContractSol.NestedStruct1[]" \
    ,"name":"","type":"tuple[]"}],"stateMutability":"view" \
    ,"type":"function"},{"inputs":[],"name":"getEmptyArray" \
    ,"outputs":[{"internalType":"uint256[]","name":"","type":"uint256[]"}] \
    ,"stateMutability":"pure","type":"function"},{"inputs":[] \
    ,"name":"getEmptyDynArrayOfStructs","outputs":[{"components":[{"internalType":"address" \
    ,"name":"a","type":"address"},{"internalType":"bytes32" \
    ,"name":"b","type":"bytes32"}],"internalType":"struct \
    TestContractSol.MyStruct[]","name":"","type":"tuple[]"}] \
    ,"stateMutability":"pure","type":"function"},{"inputs":[] \
    ,"name":"getEmptyTupleOfArrayOfStructsAndDynArrayOfStructs" \
    ,"outputs":[{"components":[{"internalType":"address" \
    ,"name":"a","type":"address"},{"internalType":"bytes32" \
    ,"name":"b","type":"bytes32"}],"internalType":"struct \
    TestContractSol.MyStruct[3]","name":"","type":"tuple[3]"} \
    ,{"components":[{"internalType":"address","name":"a" \
    ,"type":"address"},{"internalType":"bytes32","name":"b" \
    ,"type":"bytes32"}],"internalType":"struct TestContractSol.MyStruct[]" \
    ,"name":"","type":"tuple[]"}],"stateMutability":"pure" \
    ,"type":"function"},{"inputs":[],"name":"getEmptyTupleOfDynArrayStructs" \
    ,"outputs":[{"components":[{"internalType":"address" \
    ,"name":"a","type":"address"},{"internalType":"bytes32" \
    ,"name":"b","type":"bytes32"}],"internalType":"struct \
    TestContractSol.MyStruct[]","name":"","type":"tuple[]"} \
    ,{"components":[{"internalType":"address","name":"a" \
    ,"type":"address"},{"internalType":"bytes32","name":"b" \
    ,"type":"bytes32"}],"internalType":"struct TestContractSol.MyStruct[]" \
    ,"name":"","type":"tuple[]"}],"stateMutability":"pure" \
    ,"type":"function"},{"inputs":[],"name":"getEmptyTupleOfIntAndDynArray" \
    ,"outputs":[{"internalType":"uint256[]","name":"","type":"uint256[]"} \
    ,{"components":[{"internalType":"address","name":"a" \
    ,"type":"address"},{"internalType":"bytes32","name":"b" \
    ,"type":"bytes32"}],"internalType":"struct TestContractSol.MyStruct[]" \
    ,"name":"","type":"tuple[]"}],"stateMutability":"pure" \
    ,"type":"function"},{"inputs":[],"name":"getFilledArray" \
    ,"outputs":[{"internalType":"uint256[3]","name":"" \
    ,"type":"uint256[3]"}],"stateMutability":"pure","type":"function"} \
    ,{"inputs":[],"name":"getNamedSingleItem","outputs":[{"internalType":"uint256" \
    ,"name":"foo","type":"uint256"}],"stateMutability":"pure" \
    ,"type":"function"},{"inputs":[],"name":"getNestedAddressArray" \
    ,"outputs":[{"internalType":"address[3][]","name":"" \
    ,"type":"address[3][]"}],"stateMutability":"view","type":"function"} \
    ,{"inputs":[],"name":"getNestedArrayDynamicFixed","outputs":[{"internalType":"uint256[2][]" \
    ,"name":"","type":"uint256[2][]"}],"stateMutability":"pure" \
    ,"type":"function"},{"inputs":[],"name":"getNestedArrayFixedDynamic" \
    ,"outputs":[{"internalType":"uint256[][3]","name":"" \
    ,"type":"uint256[][3]"}],"stateMutability":"view","type":"function"} \
    ,{"inputs":[],"name":"getNestedArrayFixedFixed","outputs":[{"internalType":"uint256[2][3]" \
    ,"name":"","type":"uint256[2][3]"}],"stateMutability":"pure" \
    ,"type":"function"},{"inputs":[],"name":"getNestedArrayMixedDynamic" \
    ,"outputs":[{"internalType":"uint256[][3][][5]","name":"" \
    ,"type":"uint256[][3][][5]"}],"stateMutability":"view" \
    ,"type":"function"},{"inputs":[],"name":"getNestedStruct1" \
    ,"outputs":[{"components":[{"components":[{"internalType":"address" \
    ,"name":"a","type":"address"},{"internalType":"bytes32" \
    ,"name":"b","type":"bytes32"}],"internalType":"struct \
    TestContractSol.MyStruct","name":"t","type":"tuple"} \
    ,{"internalType":"uint256","name":"foo","type":"uint256"}] \
    ,"internalType":"struct TestContractSol.NestedStruct1" \
    ,"name":"","type":"tuple"}],"stateMutability":"view" \
    ,"type":"function"},{"inputs":[],"name":"getNestedStruct2" \
    ,"outputs":[{"components":[{"internalType":"uint256" \
    ,"name":"foo","type":"uint256"},{"components":[{"internalType":"address" \
    ,"name":"a","type":"address"},{"internalType":"bytes32" \
    ,"name":"b","type":"bytes32"}],"internalType":"struct \
    TestContractSol.MyStruct","name":"t","type":"tuple"}] \
    ,"internalType":"struct TestContractSol.NestedStruct2" \
    ,"name":"","type":"tuple"}],"stateMutability":"view" \
    ,"type":"function"},{"inputs":[],"name":"getNestedStructWithTuple1" \
    ,"outputs":[{"components":[{"components":[{"internalType":"address" \
    ,"name":"a","type":"address"},{"internalType":"bytes32" \
    ,"name":"b","type":"bytes32"}],"internalType":"struct \
    TestContractSol.MyStruct","name":"t","type":"tuple"} \
    ,{"internalType":"uint256","name":"foo","type":"uint256"}] \
    ,"internalType":"struct TestContractSol.NestedStruct1" \
    ,"name":"","type":"tuple"},{"internalType":"uint256" \
    ,"name":"","type":"uint256"}],"stateMutability":"view" \
    ,"type":"function"},{"inputs":[],"name":"getNestedStructWithTuple2" \
    ,"outputs":[{"internalType":"uint256","name":"","type":"uint256"} \
    ,{"components":[{"internalType":"uint256","name":"foo" \
    ,"type":"uint256"},{"components":[{"internalType":"address" \
    ,"name":"a","type":"address"},{"internalType":"bytes32" \
    ,"name":"b","type":"bytes32"}],"internalType":"struct \
    TestContractSol.MyStruct","name":"t","type":"tuple"}] \
    ,"internalType":"struct TestContractSol.NestedStruct2" \
    ,"name":"","type":"tuple"}],"stateMutability":"view" \
    ,"type":"function"},{"inputs":[],"name":"getPartiallyNamedTuple" \
    ,"outputs":[{"internalType":"uint256","name":"foo" \
    ,"type":"uint256"},{"internalType":"uint256","name":"" \
    ,"type":"uint256"}],"stateMutability":"pure","type":"function"} \
    ,{"inputs":[],"name":"getSingleItemArray","outputs":[{"internalType":"uint256[1]" \
    ,"name":"","type":"uint256[1]"}],"stateMutability":"pure" \
    ,"type":"function"},{"inputs":[],"name":"getStaticStructArray" \
    ,"outputs":[{"components":[{"internalType":"uint256" \
    ,"name":"foo","type":"uint256"},{"components":[{"internalType":"address" \
    ,"name":"a","type":"address"},{"internalType":"bytes32" \
    ,"name":"b","type":"bytes32"}],"internalType":"struct \
    TestContractSol.MyStruct","name":"t","type":"tuple"}] \
    ,"internalType":"struct TestContractSol.NestedStruct2[3]" \
    ,"name":"","type":"tuple[3]"}],"stateMutability":"view" \
    ,"type":"function"},{"inputs":[],"name":"getStruct" \
    ,"outputs":[{"components":[{"internalType":"address" \
    ,"name":"a","type":"address"},{"internalType":"bytes32" \
    ,"name":"b","type":"bytes32"}],"internalType":"struct \
    TestContractSol.MyStruct","name":"","type":"tuple"}] \
    ,"stateMutability":"view","type":"function"},{"inputs":[] \
    ,"name":"getStructWithArray","outputs":[{"components":[{"internalType":"uint256" \
    ,"name":"foo","type":"uint256"},{"components":[{"internalType":"address" \
    ,"name":"a","type":"address"},{"internalType":"bytes32" \
    ,"name":"b","type":"bytes32"}],"internalType":"struct \
    TestContractSol.MyStruct[2]","name":"arr","type":"tuple[2]"} \
    ,{"internalType":"uint256","name":"bar","type":"uint256"}] \
    ,"internalType":"struct TestContractSol.WithArray" \
    ,"name":"","type":"tuple"}],"stateMutability":"view" \
    ,"type":"function"},{"inputs":[],"name":"getTupleAllNamed" \
    ,"outputs":[{"internalType":"uint256","name":"foo" \
    ,"type":"uint256"},{"internalType":"uint256","name":"bar" \
    ,"type":"uint256"}],"stateMutability":"pure","type":"function"} \
    ,{"inputs":[],"name":"getTupleOfAddressArray","outputs":[{"internalType":"address[20]" \
    ,"name":"","type":"address[20]"},{"internalType":"int128[20]" \
    ,"name":"","type":"int128[20]"}],"stateMutability":"view" \
    ,"type":"function"},{"inputs":[],"name":"getTupleOfArrays" \
    ,"outputs":[{"internalType":"uint256[20]","name":"" \
    ,"type":"uint256[20]"},{"internalType":"uint256[20]" \
    ,"name":"","type":"uint256[20]"}],"stateMutability":"pure" \
    ,"type":"function"},{"inputs":[],"name":"getTupleOfIntAndStructArray" \
    ,"outputs":[{"internalType":"uint256","name":"","type":"uint256"} \
    ,{"components":[{"internalType":"uint256","name":"one" \
    ,"type":"uint256"},{"internalType":"uint256","name":"two" \
    ,"type":"uint256"},{"internalType":"uint256","name":"three" \
    ,"type":"uint256"},{"internalType":"uint256","name":"four" \
    ,"type":"uint256"},{"internalType":"uint256","name":"five" \
    ,"type":"uint256"},{"internalType":"uint256","name":"six" \
    ,"type":"uint256"}],"internalType":"struct TestContractSol.IntStruct[5]" \
    ,"name":"","type":"tuple[5]"}],"stateMutability":"pure" \
    ,"type":"function"},{"inputs":[],"name":"getUnnamedTuple" \
    ,"outputs":[{"internalType":"uint256","name":"","type":"uint256"} \
    ,{"internalType":"uint256","name":"","type":"uint256"}] \
    ,"stateMutability":"pure","type":"function"},{"inputs":[] \
    ,"name":"myNumber","outputs":[{"internalType":"uint256" \
    ,"name":"","type":"uint256"}],"stateMutability":"view" \
    ,"type":"function"},{"inputs":[],"name":"owner","outputs":[{"internalType":"address" \
    ,"name":"","type":"address"}],"stateMutability":"view" \
    ,"type":"function"},{"inputs":[],"name":"prevNumber" \
    ,"outputs":[{"internalType":"uint256","name":"","type":"uint256"}] \
    ,"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address" \
    ,"name":"_address","type":"address"}],"name":"setAddress" \
    ,"outputs":[],"stateMutability":"nonpayable","type":"function"} \
    ,{"inputs":[{"internalType":"address","name":"_address" \
    ,"type":"address"},{"internalType":"uint256","name":"bal" \
    ,"type":"uint256"}],"name":"setBalance","outputs":[] \
    ,"stateMutability":"nonpayable","type":"function"} \
    ,{"inputs":[{"internalType":"uint256","name":"num" \
    ,"type":"uint256"}],"name":"setNumber","outputs":[] \
    ,"stateMutability":"nonpayable","type":"function"} \
    ,{"inputs":[{"internalType":"uint256","name":"num" \
    ,"type":"uint256"},{"internalType":"address","name":"_address" \
    ,"type":"address"}],"name":"setNumber","outputs":[] \
    ,"stateMutability":"nonpayable","type":"function"} \
    ,{"inputs":[{"components":[{"internalType":"address" \
    ,"name":"a","type":"address"},{"internalType":"bytes32" \
    ,"name":"b","type":"bytes32"}],"internalType":"struct \
    TestContractSol.MyStruct","name":"_my_struct","type":"tuple"}] \
    ,"name":"setStruct","outputs":[],"stateMutability":"pure" \
    ,"type":"function"},{"inputs":[{"components":[{"internalType":"address" \
    ,"name":"a","type":"address"},{"internalType":"bytes32" \
    ,"name":"b","type":"bytes32"}],"internalType":"struct \
    TestContractSol.MyStruct[2]","name":"_my_struct_array" \
    ,"type":"tuple[2]"}],"name":"setStructArray","outputs":[] \
    ,"stateMutability":"pure","type":"function"},{"inputs":[] \
    ,"name":"theAddress","outputs":[{"internalType":"address" \
    ,"name":"","type":"address"}],"stateMutability":"view" \
    ,"type":"function"}]'


@pytest.fixture
def vyper_contract_instance_abi():
    return '[{"anonymous":false,"inputs":[{"indexed":false \
    ,"name":"b","type":"bytes32"},{"indexed":false \
    ,"name":"prevNum","type":"uint256"},{"indexed":false \
    ,"name":"dynData","type":"string"},{"indexed":true \
    ,"name":"newNum","type":"uint256"},{"indexed":true \
    ,"name":"dynIndexed","type":"string"}],"name":"NumberChange" \
    ,"type":"event"},{"anonymous":false,"inputs":[{"indexed":true \
    ,"name":"newAddress","type":"address"}],"name":"AddressChange" \
    ,"type":"event"},{"anonymous":false,"inputs":[{"indexed":true \
    ,"name":"foo","type":"uint256"}],"name":"FooHappened" \
    ,"type":"event"},{"anonymous":false,"inputs":[{"indexed":true \
    ,"name":"bar","type":"uint256"}],"name":"BarHappened" \
    ,"type":"event"},{"inputs":[{"name":"num" \
    ,"type":"uint256"}],"stateMutability":"nonpayable" \
    ,"type":"constructor"},{"inputs":[],"name":"fooAndBar" \
    ,"outputs":[],"stateMutability":"nonpayable" \
    ,"type":"function"},{"inputs":[{"name":"num" \
    ,"type":"uint256"}],"name":"setNumber","outputs":[] \
    ,"stateMutability":"nonpayable","type":"function"} \
    ,{"inputs":[{"name":"_address","type":"address"}] \
    ,"name":"setAddress","outputs":[],"stateMutability":"nonpayable" \
    ,"type":"function"},{"inputs":[{"name":"_address" \
    ,"type":"address"},{"name":"bal","type":"uint256"}] \
    ,"name":"setBalance","outputs":[],"stateMutability":"nonpayable" \
    ,"type":"function"},{"inputs":[],"name":"getStruct" \
    ,"outputs":[{"components":[{"name":"a","type":"address"} \
    ,{"name":"b","type":"bytes32"}],"name":"" \
    ,"type":"tuple"}],"stateMutability":"view" \
    ,"type":"function"},{"inputs":[],"name":"getNestedStruct1" \
    ,"outputs":[{"components":[{"components":[{"name":"a" \
    ,"type":"address"},{"name":"b","type":"bytes32"}] \
    ,"name":"t","type":"tuple"},{"name":"foo" \
    ,"type":"uint256"}],"name":"","type":"tuple"}] \
    ,"stateMutability":"view","type":"function"} \
    ,{"inputs":[],"name":"getNestedStruct2","outputs":[{"components":[{"name":"foo" \
    ,"type":"uint256"},{"components":[{"name":"a" \
    ,"type":"address"},{"name":"b","type":"bytes32"}] \
    ,"name":"t","type":"tuple"}],"name":"","type":"tuple"}] \
    ,"stateMutability":"view","type":"function"} \
    ,{"inputs":[],"name":"getNestedStructWithTuple1" \
    ,"outputs":[{"components":[{"components":[{"name":"a" \
    ,"type":"address"},{"name":"b","type":"bytes32"}] \
    ,"name":"t","type":"tuple"},{"name":"foo" \
    ,"type":"uint256"}],"name":"","type":"tuple"} \
    ,{"name":"","type":"uint256"}],"stateMutability":"view" \
    ,"type":"function"},{"inputs":[],"name":"getNestedStructWithTuple2" \
    ,"outputs":[{"name":"","type":"uint256"} \
    ,{"components":[{"name":"foo","type":"uint256"} \
    ,{"components":[{"name":"a","type":"address"} \
    ,{"name":"b","type":"bytes32"}],"name":"t" \
    ,"type":"tuple"}],"name":"","type":"tuple"}] \
    ,"stateMutability":"view","type":"function"} \
    ,{"inputs":[],"name":"getEmptyDynArrayOfStructs" \
    ,"outputs":[{"components":[{"name":"a","type":"address"} \
    ,{"name":"b","type":"bytes32"}],"name":"" \
    ,"type":"tuple[]"}],"stateMutability":"pure" \
    ,"type":"function"},{"inputs":[],"name":"getEmptyTupleOfDynArrayStructs" \
    ,"outputs":[{"components":[{"name":"a","type":"address"} \
    ,{"name":"b","type":"bytes32"}],"name":"" \
    ,"type":"tuple[]"},{"components":[{"name":"a" \
    ,"type":"address"},{"name":"b","type":"bytes32"}] \
    ,"name":"","type":"tuple[]"}],"stateMutability":"pure" \
    ,"type":"function"},{"inputs":[],"name":"getEmptyTupleOfArrayOfStructsAndDynArrayOfStructs" \
    ,"outputs":[{"components":[{"name":"a","type":"address"} \
    ,{"name":"b","type":"bytes32"}],"name":"" \
    ,"type":"tuple[3]"},{"components":[{"name":"a" \
    ,"type":"address"},{"name":"b","type":"bytes32"}] \
    ,"name":"","type":"tuple[]"}],"stateMutability":"view" \
    ,"type":"function"},{"inputs":[],"name":"getTupleOfIntAndStructArray" \
    ,"outputs":[{"name":"","type":"uint256"} \
    ,{"components":[{"name":"one","type":"uint256"} \
    ,{"name":"two","type":"uint256"},{"name":"three" \
    ,"type":"uint256"},{"name":"four","type":"uint256"} \
    ,{"name":"five","type":"uint256"},{"name":"six" \
    ,"type":"uint256"}],"name":"","type":"tuple[5]"}] \
    ,"stateMutability":"view","type":"function"} \
    ,{"inputs":[],"name":"getEmptyTupleOfIntAndDynArray" \
    ,"outputs":[{"name":"","type":"uint256[]"} \
    ,{"components":[{"name":"a","type":"address"} \
    ,{"name":"b","type":"bytes32"}],"name":"" \
    ,"type":"tuple[]"}],"stateMutability":"pure" \
    ,"type":"function"},{"inputs":[],"name":"getStructWithArray" \
    ,"outputs":[{"components":[{"name":"foo" \
    ,"type":"uint256"},{"components":[{"name":"a" \
    ,"type":"address"},{"name":"b","type":"bytes32"}] \
    ,"name":"arr","type":"tuple[2]"},{"name":"bar" \
    ,"type":"uint256"}],"name":"","type":"tuple"}] \
    ,"stateMutability":"view","type":"function"} \
    ,{"inputs":[],"name":"getEmptyArray","outputs":[{"name":"" \
    ,"type":"uint256[]"}],"stateMutability":"pure" \
    ,"type":"function"},{"inputs":[],"name":"getSingleItemArray" \
    ,"outputs":[{"name":"","type":"uint256[]"}] \
    ,"stateMutability":"pure","type":"function"} \
    ,{"inputs":[],"name":"getFilledArray","outputs":[{"name":"" \
    ,"type":"uint256[]"}],"stateMutability":"pure" \
    ,"type":"function"},{"inputs":[],"name":"getAddressArray" \
    ,"outputs":[{"name":"","type":"address[]"}] \
    ,"stateMutability":"view","type":"function"} \
    ,{"inputs":[],"name":"getDynamicStructArray" \
    ,"outputs":[{"components":[{"components":[{"name":"a" \
    ,"type":"address"},{"name":"b","type":"bytes32"}] \
    ,"name":"t","type":"tuple"},{"name":"foo" \
    ,"type":"uint256"}],"name":"","type":"tuple[]"}] \
    ,"stateMutability":"view","type":"function"} \
    ,{"inputs":[],"name":"getStaticStructArray" \
    ,"outputs":[{"components":[{"name":"foo" \
    ,"type":"uint256"},{"components":[{"name":"a" \
    ,"type":"address"},{"name":"b","type":"bytes32"}] \
    ,"name":"t","type":"tuple"}],"name":"","type":"tuple[2]"}] \
    ,"stateMutability":"view","type":"function"} \
    ,{"inputs":[],"name":"getArrayWithBiggerSize" \
    ,"outputs":[{"name":"","type":"uint256[20]"}] \
    ,"stateMutability":"pure","type":"function"} \
    ,{"inputs":[],"name":"getTupleOfArrays","outputs":[{"name":"" \
    ,"type":"uint256[20]"},{"name":"","type":"uint256[20]"}] \
    ,"stateMutability":"pure","type":"function"} \
    ,{"inputs":[],"name":"getMultipleValues" \
    ,"outputs":[{"name":"","type":"uint256"} \
    ,{"name":"","type":"uint256"}],"stateMutability":"pure" \
    ,"type":"function"},{"inputs":[],"name":"getUnnamedTuple" \
    ,"outputs":[{"name":"","type":"uint256"} \
    ,{"name":"","type":"uint256"}],"stateMutability":"pure" \
    ,"type":"function"},{"inputs":[],"name":"getTupleOfAddressArray" \
    ,"outputs":[{"name":"","type":"address[20]"} \
    ,{"name":"","type":"uint128[20]"}],"stateMutability":"view" \
    ,"type":"function"},{"inputs":[],"name":"getNestedArrayFixedFixed" \
    ,"outputs":[{"name":"","type":"uint256[2][3]"}] \
    ,"stateMutability":"view","type":"function"} \
    ,{"inputs":[],"name":"getNestedArrayDynamicFixed" \
    ,"outputs":[{"name":"","type":"uint256[2][]"}] \
    ,"stateMutability":"view","type":"function"} \
    ,{"inputs":[],"name":"getNestedArrayFixedDynamic" \
    ,"outputs":[{"name":"","type":"uint256[][3]"}] \
    ,"stateMutability":"view","type":"function"} \
    ,{"inputs":[],"name":"getNestedArrayMixedDynamic" \
    ,"outputs":[{"name":"","type":"uint256[][3][][5]"}] \
    ,"stateMutability":"view","type":"function"} \
    ,{"inputs":[],"name":"getNestedAddressArray" \
    ,"outputs":[{"name":"","type":"address[3][]"}] \
    ,"stateMutability":"view","type":"function"} \
    ,{"inputs":[{"name":"a0","type":"uint256"} \
    ,{"name":"a1","type":"uint256"},{"name":"a2" \
    ,"type":"uint256"},{"name":"a3","type":"uint256"} \
    ,{"name":"a4","type":"uint256"},{"name":"a5" \
    ,"type":"uint256"},{"name":"a6","type":"uint256"} \
    ,{"name":"a7","type":"uint256"},{"name":"a8" \
    ,"type":"uint256"},{"name":"a9","type":"uint256"}] \
    ,"name":"functionWithUniqueAmountOfArguments" \
    ,"outputs":[],"stateMutability":"view","type":"function"} \
    ,{"inputs":[{"components":[{"name":"a","type":"address"} \
    ,{"name":"b","type":"bytes32"}],"name":"_my_struct" \
    ,"type":"tuple"}],"name":"setStruct","outputs":[] \
    ,"stateMutability":"pure","type":"function"} \
    ,{"inputs":[{"components":[{"name":"a","type":"address"} \
    ,{"name":"b","type":"bytes32"}],"name":"_my_struct_array" \
    ,"type":"tuple[2]"}],"name":"setStructArray" \
    ,"outputs":[],"stateMutability":"pure","type":"function"} \
    ,{"inputs":[],"name":"owner","outputs":[{"name":"" \
    ,"type":"address"}],"stateMutability":"view" \
    ,"type":"function"},{"inputs":[],"name":"myNumber" \
    ,"outputs":[{"name":"","type":"uint256"}] \
    ,"stateMutability":"view","type":"function"} \
    ,{"inputs":[],"name":"prevNumber","outputs":[{"name":"" \
    ,"type":"uint256"}],"stateMutability":"view" \
    ,"type":"function"},{"inputs":[],"name":"theAddress" \
    ,"outputs":[{"name":"","type":"address"}] \
    ,"stateMutability":"view","type":"function"} \
    ,{"inputs":[{"name":"arg0","type":"address"}] \
    ,"name":"balances","outputs":[{"name":"" \
    ,"type":"uint256"}],"stateMutability":"view" \
    ,"type":"function"},{"inputs":[{"name":"arg0" \
    ,"type":"uint256"},{"name":"arg1","type":"uint256"}] \
    ,"name":"dynArray","outputs":[{"name":"" \
    ,"type":"uint256"}],"stateMutability":"view" \
    ,"type":"function"},{"inputs":[{"name":"arg0" \
    ,"type":"uint256"},{"name":"arg1","type":"uint256"} \
    ,{"name":"arg2","type":"uint256"},{"name":"arg3" \
    ,"type":"uint256"}],"name":"mixedArray","outputs":[{"name":"" \
    ,"type":"uint256"}],"stateMutability":"view" \
    ,"type":"function"}],"ast":{"ast_type":"Module" \
    ,"children":[{"ast_type":"EventDef","children":[{"ast_type":"AnnAssign" \
    ,"children":[{"ast_type":"Name","children":[] \
    ,"classification":0,"col_offset":7,"end_col_offset":14 \
    ,"end_lineno":4,"lineno":4,"src":{"jump_code":"" \
    ,"length":7,"start":45}},{"ast_type":"Name" \
    ,"children":[],"classification":0,"col_offset":4 \
    ,"end_col_offset":5,"end_lineno":4,"lineno":4 \
    ,"src":{"jump_code":"","length":1,"start":42}}] \
    ,"classification":0,"col_offset":4,"end_col_offset":14 \
    ,"end_lineno":4,"lineno":4,"src":{"jump_code":"" \
    ,"length":10,"start":42}},{"ast_type":"AnnAssign" \
    ,"children":[{"ast_type":"Name","children":[] \
    ,"classification":0,"col_offset":13,"end_col_offset":20 \
    ,"end_lineno":5,"lineno":5,"src":{"jump_code":"" \
    ,"length":7,"start":66}},{"ast_type":"Name" \
    ,"children":[],"classification":0,"col_offset":4 \
    ,"end_col_offset":11,"end_lineno":5,"lineno":5 \
    ,"src":{"jump_code":"","length":7,"start":57}}] \
    ,"classification":0,"col_offset":4,"end_col_offset":20 \
    ,"end_lineno":5,"lineno":5,"src":{"jump_code":"" \
    ,"length":16,"start":57}},{"ast_type":"AnnAssign" \
    ,"children":[{"ast_type":"Subscript","children":[{"ast_type":"Index" \
    ,"children":[{"ast_type":"Int","children":[] \
    ,"classification":0,"col_offset":20,"end_col_offset":22 \
    ,"end_lineno":6,"lineno":6,"src":{"jump_code":"" \
    ,"length":2,"start":94}}],"classification":0 \
    ,"col_offset":20,"end_col_offset":22,"end_lineno":6 \
    ,"lineno":6,"src":{"jump_code":"","length":2 \
    ,"start":94}},{"ast_type":"Name","children":[] \
    ,"classification":0,"col_offset":13,"end_col_offset":19 \
    ,"end_lineno":6,"lineno":6,"src":{"jump_code":"" \
    ,"length":6,"start":87}}],"classification":0 \
    ,"col_offset":13,"end_col_offset":23,"end_lineno":6 \
    ,"lineno":6,"src":{"jump_code":"","length":10 \
    ,"start":87}},{"ast_type":"Name","children":[] \
    ,"classification":0,"col_offset":4,"end_col_offset":11 \
    ,"end_lineno":6,"lineno":6,"src":{"jump_code":"" \
    ,"length":7,"start":78}}],"classification":0 \
    ,"col_offset":4,"end_col_offset":23,"end_lineno":6 \
    ,"lineno":6,"src":{"jump_code":"","length":19 \
    ,"start":78}},{"ast_type":"AnnAssign","children":[{"ast_type":"Call" \
    ,"children":[{"ast_type":"Name","children":[] \
    ,"classification":0,"col_offset":20,"end_col_offset":27 \
    ,"end_lineno":7,"lineno":7,"src":{"jump_code":"" \
    ,"length":7,"start":118}},{"ast_type":"Name" \
    ,"children":[],"classification":0,"col_offset":12 \
    ,"end_col_offset":19,"end_lineno":7,"lineno":7 \
    ,"src":{"jump_code":"","length":7,"start":110}}] \
    ,"classification":0,"col_offset":12,"end_col_offset":28 \
    ,"end_lineno":7,"lineno":7,"src":{"jump_code":"" \
    ,"length":16,"start":110}},{"ast_type":"Name" \
    ,"children":[],"classification":0,"col_offset":4 \
    ,"end_col_offset":10,"end_lineno":7,"lineno":7 \
    ,"src":{"jump_code":"","length":6,"start":102}}] \
    ,"classification":0,"col_offset":4,"end_col_offset":28 \
    ,"end_lineno":7,"lineno":7,"src":{"jump_code":"" \
    ,"length":24,"start":102}},{"ast_type":"AnnAssign" \
    ,"children":[{"ast_type":"Call","children":[{"ast_type":"Subscript" \
    ,"children":[{"ast_type":"Index","children":[{"ast_type":"Int" \
    ,"children":[],"classification":0,"col_offset":31 \
    ,"end_col_offset":33,"end_lineno":8,"lineno":8 \
    ,"src":{"jump_code":"","length":2,"start":158}}] \
    ,"classification":0,"col_offset":31,"end_col_offset":33 \
    ,"end_lineno":8,"lineno":8,"src":{"jump_code":"" \
    ,"length":2,"start":158}},{"ast_type":"Name" \
    ,"children":[],"classification":0,"col_offset":24 \
    ,"end_col_offset":30,"end_lineno":8,"lineno":8 \
    ,"src":{"jump_code":"","length":6,"start":151}}] \
    ,"classification":0,"col_offset":24,"end_col_offset":34 \
    ,"end_lineno":8,"lineno":8,"src":{"jump_code":"" \
    ,"length":10,"start":151}},{"ast_type":"Name" \
    ,"children":[],"classification":0,"col_offset":16 \
    ,"end_col_offset":23,"end_lineno":8,"lineno":8 \
    ,"src":{"jump_code":"","length":7,"start":143}}] \
    ,"classification":0,"col_offset":16,"end_col_offset":35 \
    ,"end_lineno":8,"lineno":8,"src":{"jump_code":"" \
    ,"length":19,"start":143}},{"ast_type":"Name" \
    ,"children":[],"classification":0,"col_offset":4 \
    ,"end_col_offset":14,"end_lineno":8,"lineno":8 \
    ,"src":{"jump_code":"","length":10,"start":131}}] \
    ,"classification":0,"col_offset":4,"end_col_offset":35 \
    ,"end_lineno":8,"lineno":8,"src":{"jump_code":"" \
    ,"length":31,"start":131}}],"classification":0 \
    ,"col_offset":0,"end_col_offset":35,"end_lineno":8 \
    ,"lineno":3,"src":{"jump_code":"","length":144 \
    ,"start":18}},{"ast_type":"EventDef","children":[{"ast_type":"AnnAssign" \
    ,"children":[{"ast_type":"Call","children":[{"ast_type":"Name" \
    ,"children":[],"classification":0,"col_offset":24 \
    ,"end_col_offset":31,"end_lineno":11,"lineno":11 \
    ,"src":{"jump_code":"","length":7,"start":209}} \
    ,{"ast_type":"Name","children":[],"classification":0 \
    ,"col_offset":16,"end_col_offset":23,"end_lineno":11 \
    ,"lineno":11,"src":{"jump_code":"","length":7 \
    ,"start":201}}],"classification":0,"col_offset":16 \
    ,"end_col_offset":32,"end_lineno":11,"lineno":11 \
    ,"src":{"jump_code":"","length":16,"start":201}} \
    ,{"ast_type":"Name","children":[],"classification":0 \
    ,"col_offset":4,"end_col_offset":14,"end_lineno":11 \
    ,"lineno":11,"src":{"jump_code":"","length":10 \
    ,"start":189}}],"classification":0,"col_offset":4 \
    ,"end_col_offset":32,"end_lineno":11,"lineno":11 \
    ,"src":{"jump_code":"","length":28,"start":189}}] \
    ,"classification":0,"col_offset":0,"end_col_offset":32 \
    ,"end_lineno":11,"lineno":10,"src":{"jump_code":"" \
    ,"length":53,"start":164}},{"ast_type":"EventDef" \
    ,"children":[{"ast_type":"AnnAssign","children":[{"ast_type":"Call" \
    ,"children":[{"ast_type":"Name","children":[] \
    ,"classification":0,"col_offset":17,"end_col_offset":24 \
    ,"end_lineno":14,"lineno":14,"src":{"jump_code":"" \
    ,"length":7,"start":255}},{"ast_type":"Name" \
    ,"children":[],"classification":0,"col_offset":9 \
    ,"end_col_offset":16,"end_lineno":14,"lineno":14 \
    ,"src":{"jump_code":"","length":7,"start":247}}] \
    ,"classification":0,"col_offset":9,"end_col_offset":25 \
    ,"end_lineno":14,"lineno":14,"src":{"jump_code":"" \
    ,"length":16,"start":247}},{"ast_type":"Name" \
    ,"children":[],"classification":0,"col_offset":4 \
    ,"end_col_offset":7,"end_lineno":14,"lineno":14 \
    ,"src":{"jump_code":"","length":3,"start":242}}] \
    ,"classification":0,"col_offset":4,"end_col_offset":25 \
    ,"end_lineno":14,"lineno":14,"src":{"jump_code":"" \
    ,"length":21,"start":242}}],"classification":0 \
    ,"col_offset":0,"end_col_offset":25,"end_lineno":14 \
    ,"lineno":13,"src":{"jump_code":"","length":44 \
    ,"start":219}},{"ast_type":"EventDef","children":[{"ast_type":"AnnAssign" \
    ,"children":[{"ast_type":"Call","children":[{"ast_type":"Name" \
    ,"children":[],"classification":0,"col_offset":17 \
    ,"end_col_offset":24,"end_lineno":17,"lineno":17 \
    ,"src":{"jump_code":"","length":7,"start":301}} \
    ,{"ast_type":"Name","children":[],"classification":0 \
    ,"col_offset":9,"end_col_offset":16,"end_lineno":17 \
    ,"lineno":17,"src":{"jump_code":"","length":7 \
    ,"start":293}}],"classification":0,"col_offset":9 \
    ,"end_col_offset":25,"end_lineno":17,"lineno":17 \
    ,"src":{"jump_code":"","length":16,"start":293}} \
    ,{"ast_type":"Name","children":[],"classification":0 \
    ,"col_offset":4,"end_col_offset":7,"end_lineno":17 \
    ,"lineno":17,"src":{"jump_code":"","length":3 \
    ,"start":288}}],"classification":0,"col_offset":4 \
    ,"end_col_offset":25,"end_lineno":17,"lineno":17 \
    ,"src":{"jump_code":"","length":21,"start":288}}] \
    ,"classification":0,"col_offset":0,"end_col_offset":25 \
    ,"end_lineno":17,"lineno":16,"src":{"jump_code":"" \
    ,"length":44,"start":265}},{"ast_type":"StructDef" \
    ,"children":[{"ast_type":"AnnAssign","children":[{"ast_type":"Name" \
    ,"children":[],"classification":0,"col_offset":7 \
    ,"end_col_offset":14,"end_lineno":20,"lineno":20 \
    ,"src":{"jump_code":"","length":7,"start":335}} \
    ,{"ast_type":"Name","children":[],"classification":0 \
    ,"col_offset":4,"end_col_offset":5,"end_lineno":20 \
    ,"lineno":20,"src":{"jump_code":"","length":1 \
    ,"start":332}}],"classification":0,"col_offset":4 \
    ,"end_col_offset":14,"end_lineno":20,"lineno":20 \
    ,"src":{"jump_code":"","length":10,"start":332}} \
    ,{"ast_type":"AnnAssign","children":[{"ast_type":"Name" \
    ,"children":[],"classification":0,"col_offset":7 \
    ,"end_col_offset":14,"end_lineno":21,"lineno":21 \
    ,"src":{"jump_code":"","length":7,"start":350}} \
    ,{"ast_type":"Name","children":[],"classification":0 \
    ,"col_offset":4,"end_col_offset":5,"end_lineno":21 \
    ,"lineno":21,"src":{"jump_code":"","length":1 \
    ,"start":347}}],"classification":0,"col_offset":4 \
    ,"end_col_offset":14,"end_lineno":21,"lineno":21 \
    ,"src":{"jump_code":"","length":10,"start":347}}] \
    ,"classification":0,"col_offset":0,"end_col_offset":14 \
    ,"end_lineno":21,"lineno":19,"src":{"jump_code":"" \
    ,"length":46,"start":311}},{"ast_type":"StructDef" \
    ,"children":[{"ast_type":"AnnAssign","children":[{"ast_type":"Name" \
    ,"children":[],"classification":0,"col_offset":7 \
    ,"end_col_offset":15,"end_lineno":24,"lineno":24 \
    ,"src":{"jump_code":"","length":8,"start":388}} \
    ,{"ast_type":"Name","children":[],"classification":0 \
    ,"col_offset":4,"end_col_offset":5,"end_lineno":24 \
    ,"lineno":24,"src":{"jump_code":"","length":1 \
    ,"start":385}}],"classification":0,"col_offset":4 \
    ,"end_col_offset":15,"end_lineno":24,"lineno":24 \
    ,"src":{"jump_code":"","length":11,"start":385}} \
    ,{"ast_type":"AnnAssign","children":[{"ast_type":"Name" \
    ,"children":[],"classification":0,"col_offset":9 \
    ,"end_col_offset":16,"end_lineno":25,"lineno":25 \
    ,"src":{"jump_code":"","length":7,"start":406}} \
    ,{"ast_type":"Name","children":[],"classification":0 \
    ,"col_offset":4,"end_col_offset":7,"end_lineno":25 \
    ,"lineno":25,"src":{"jump_code":"","length":3 \
    ,"start":401}}],"classification":0,"col_offset":4 \
    ,"end_col_offset":16,"end_lineno":25,"lineno":25 \
    ,"src":{"jump_code":"","length":12,"start":401}}] \
    ,"classification":0,"col_offset":0,"end_col_offset":16 \
    ,"end_lineno":25,"lineno":23,"src":{"jump_code":"" \
    ,"length":54,"start":359}},{"ast_type":"StructDef" \
    ,"children":[{"ast_type":"AnnAssign","children":[{"ast_type":"Name" \
    ,"children":[],"classification":0,"col_offset":9 \
    ,"end_col_offset":16,"end_lineno":28,"lineno":28 \
    ,"src":{"jump_code":"","length":7,"start":446}} \
    ,{"ast_type":"Name","children":[],"classification":0 \
    ,"col_offset":4,"end_col_offset":7,"end_lineno":28 \
    ,"lineno":28,"src":{"jump_code":"","length":3 \
    ,"start":441}}],"classification":0,"col_offset":4 \
    ,"end_col_offset":16,"end_lineno":28,"lineno":28 \
    ,"src":{"jump_code":"","length":12,"start":441}} \
    ,{"ast_type":"AnnAssign","children":[{"ast_type":"Name" \
    ,"children":[],"classification":0,"col_offset":7 \
    ,"end_col_offset":15,"end_lineno":29,"lineno":29 \
    ,"src":{"jump_code":"","length":8,"start":461}} \
    ,{"ast_type":"Name","children":[],"classification":0 \
    ,"col_offset":4,"end_col_offset":5,"end_lineno":29 \
    ,"lineno":29,"src":{"jump_code":"","length":1 \
    ,"start":458}}],"classification":0,"col_offset":4 \
    ,"end_col_offset":15,"end_lineno":29,"lineno":29 \
    ,"src":{"jump_code":"","length":11,"start":458}}] \
    ,"classification":0,"col_offset":0,"end_col_offset":15 \
    ,"end_lineno":29,"lineno":27,"src":{"jump_code":"" \
    ,"length":54,"start":415}},{"ast_type":"StructDef" \
    ,"children":[{"ast_type":"AnnAssign","children":[{"ast_type":"Name" \
    ,"children":[],"classification":0,"col_offset":9 \
    ,"end_col_offset":16,"end_lineno":32,"lineno":32 \
    ,"src":{"jump_code":"","length":7,"start":498}} \
    ,{"ast_type":"Name","children":[],"classification":0 \
    ,"col_offset":4,"end_col_offset":7,"end_lineno":32 \
    ,"lineno":32,"src":{"jump_code":"","length":3 \
    ,"start":493}}],"classification":0,"col_offset":4 \
    ,"end_col_offset":16,"end_lineno":32,"lineno":32 \
    ,"src":{"jump_code":"","length":12,"start":493}} \
    ,{"ast_type":"AnnAssign","children":[{"ast_type":"Subscript" \
    ,"children":[{"ast_type":"Index","children":[{"ast_type":"Int" \
    ,"children":[],"classification":0,"col_offset":18 \
    ,"end_col_offset":19,"end_lineno":33,"lineno":33 \
    ,"src":{"jump_code":"","length":1,"start":524}}] \
    ,"classification":0,"col_offset":18,"end_col_offset":19 \
    ,"end_lineno":33,"lineno":33,"src":{"jump_code":"" \
    ,"length":1,"start":524}},{"ast_type":"Name" \
    ,"children":[],"classification":0,"col_offset":9 \
    ,"end_col_offset":17,"end_lineno":33,"lineno":33 \
    ,"src":{"jump_code":"","length":8,"start":515}}] \
    ,"classification":0,"col_offset":9,"end_col_offset":20 \
    ,"end_lineno":33,"lineno":33,"src":{"jump_code":"" \
    ,"length":11,"start":515}},{"ast_type":"Name" \
    ,"children":[],"classification":0,"col_offset":4 \
    ,"end_col_offset":7,"end_lineno":33,"lineno":33 \
    ,"src":{"jump_code":"","length":3,"start":510}}] \
    ,"classification":0,"col_offset":4,"end_col_offset":20 \
    ,"end_lineno":33,"lineno":33,"src":{"jump_code":"" \
    ,"length":16,"start":510}},{"ast_type":"AnnAssign" \
    ,"children":[{"ast_type":"Name","children":[] \
    ,"classification":0,"col_offset":9,"end_col_offset":16 \
    ,"end_lineno":34,"lineno":34,"src":{"jump_code":"" \
    ,"length":7,"start":536}},{"ast_type":"Name" \
    ,"children":[],"classification":0,"col_offset":4 \
    ,"end_col_offset":7,"end_lineno":34,"lineno":34 \
    ,"src":{"jump_code":"","length":3,"start":531}}] \
    ,"classification":0,"col_offset":4,"end_col_offset":16 \
    ,"end_lineno":34,"lineno":34,"src":{"jump_code":"" \
    ,"length":12,"start":531}}],"classification":0 \
    ,"col_offset":0,"end_col_offset":16,"end_lineno":34 \
    ,"lineno":31,"src":{"jump_code":"","length":72 \
    ,"start":471}},{"ast_type":"StructDef","children":[{"ast_type":"AnnAssign" \
    ,"children":[{"ast_type":"Name","children":[] \
    ,"classification":0,"col_offset":9,"end_col_offset":16 \
    ,"end_lineno":37,"lineno":37,"src":{"jump_code":"" \
    ,"length":7,"start":572}},{"ast_type":"Name" \
    ,"children":[],"classification":0,"col_offset":4 \
    ,"end_col_offset":7,"end_lineno":37,"lineno":37 \
    ,"src":{"jump_code":"","length":3,"start":567}}] \
    ,"classification":0,"col_offset":4,"end_col_offset":16 \
    ,"end_lineno":37,"lineno":37,"src":{"jump_code":"" \
    ,"length":12,"start":567}},{"ast_type":"AnnAssign" \
    ,"children":[{"ast_type":"Name","children":[] \
    ,"classification":0,"col_offset":9,"end_col_offset":16 \
    ,"end_lineno":38,"lineno":38,"src":{"jump_code":"" \
    ,"length":7,"start":589}},{"ast_type":"Name" \
    ,"children":[],"classification":0,"col_offset":4 \
    ,"end_col_offset":7,"end_lineno":38,"lineno":38 \
    ,"src":{"jump_code":"","length":3,"start":584}}] \
    ,"classification":0,"col_offset":4,"end_col_offset":16 \
    ,"end_lineno":38,"lineno":38,"src":{"jump_code":"" \
    ,"length":12,"start":584}},{"ast_type":"AnnAssign" \
    ,"children":[{"ast_type":"Name","children":[] \
    ,"classification":0,"col_offset":11,"end_col_offset":18 \
    ,"end_lineno":39,"lineno":39,"src":{"jump_code":"" \
    ,"length":7,"start":608}},{"ast_type":"Name" \
    ,"children":[],"classification":0,"col_offset":4 \
    ,"end_col_offset":9,"end_lineno":39,"lineno":39 \
    ,"src":{"jump_code":"","length":5,"start":601}}] \
    ,"classification":0,"col_offset":4,"end_col_offset":18 \
    ,"end_lineno":39,"lineno":39,"src":{"jump_code":"" \
    ,"length":14,"start":601}},{"ast_type":"AnnAssign" \
    ,"children":[{"ast_type":"Name","children":[] \
    ,"classification":0,"col_offset":10,"end_col_offset":17 \
    ,"end_lineno":40,"lineno":40,"src":{"jump_code":"" \
    ,"length":7,"start":626}},{"ast_type":"Name" \
    ,"children":[],"classification":0,"col_offset":4 \
    ,"end_col_offset":8,"end_lineno":40,"lineno":40 \
    ,"src":{"jump_code":"","length":4,"start":620}}] \
    ,"classification":0,"col_offset":4,"end_col_offset":17 \
    ,"end_lineno":40,"lineno":40,"src":{"jump_code":"" \
    ,"length":13,"start":620}},{"ast_type":"AnnAssign" \
    ,"children":[{"ast_type":"Name","children":[] \
    ,"classification":0,"col_offset":10,"end_col_offset":17 \
    ,"end_lineno":41,"lineno":41,"src":{"jump_code":"" \
    ,"length":7,"start":644}},{"ast_type":"Name" \
    ,"children":[],"classification":0,"col_offset":4 \
    ,"end_col_offset":8,"end_lineno":41,"lineno":41 \
    ,"src":{"jump_code":"","length":4,"start":638}}] \
    ,"classification":0,"col_offset":4,"end_col_offset":17 \
    ,"end_lineno":41,"lineno":41,"src":{"jump_code":"" \
    ,"length":13,"start":638}},{"ast_type":"AnnAssign" \
    ,"children":[{"ast_type":"Name","children":[] \
    ,"classification":0,"col_offset":9,"end_col_offset":16 \
    ,"end_lineno":42,"lineno":42,"src":{"jump_code":"" \
    ,"length":7,"start":661}},{"ast_type":"Name" \
    ,"children":[],"classification":0,"col_offset":4 \
    ,"end_col_offset":7,"end_lineno":42,"lineno":42 \
    ,"src":{"jump_code":"","length":3,"start":656}}] \
    ,"classification":0,"col_offset":4,"end_col_offset":16 \
    ,"end_lineno":42,"lineno":42,"src":{"jump_code":"" \
    ,"length":12,"start":656}}]'
