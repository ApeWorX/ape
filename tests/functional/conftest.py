import json
import tempfile
from contextlib import contextmanager
from distutils.dir_util import copy_tree
from pathlib import Path
from typing import Dict, Optional

import pytest
import yaml
from eth.exceptions import HeaderNotFound
from ethpm_types import ContractType
from hexbytes import HexBytes

import ape
from ape.api import EcosystemAPI, NetworkAPI, PluginConfig, TransactionAPI
from ape.contracts import ContractContainer, ContractInstance
from ape.exceptions import ChainError, ContractLogicError, ProviderNotConnectedError
from ape.managers.config import CONFIG_FILE_NAME
from ape.types import AddressType, ContractLog


def _get_raw_contract(compiler: str) -> Dict:
    here = Path(__file__).parent
    contracts_dir = here / "data" / "contracts" / "ethereum" / "local"
    return json.loads((contracts_dir / f"{compiler}_contract.json").read_text())


RAW_SOLIDITY_CONTRACT_TYPE = _get_raw_contract("solidity")
RAW_VYPER_CONTRACT_TYPE = _get_raw_contract("vyper")
TEST_ADDRESS = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
BASE_PROJECTS_DIRECTORY = (Path(__file__).parent / "data" / "projects").absolute()
PROJECT_WITH_LONG_CONTRACTS_FOLDER = BASE_PROJECTS_DIRECTORY / "LongContractsFolder"
APE_PROJECT_FOLDER = BASE_PROJECTS_DIRECTORY / "ApeProject"
SOLIDITY_CONTRACT_ADDRESS = "0xBcF7FFFD8B256Ec51a36782a52D0c34f6474D951"
VYPER_CONTRACT_ADDRESS = "0x274b028b03A250cA03644E6c578D81f019eE1323"


class _ContractLogicError(ContractLogicError):
    pass


@pytest.hookimpl(trylast=True, hookwrapper=True)
def pytest_collection_finish(session):
    with ape.networks.parse_network_choice("::test"):
        # Sets the active provider
        yield


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):
    module_name = item.module.__name__
    prefix = "tests.functional"

    if module_name.startswith(prefix):
        snapshot_id = ape.chain.snapshot()
        yield

        try:
            ape.chain.restore(snapshot_id)
        except (HeaderNotFound, ChainError, ProviderNotConnectedError):
            pass
    else:
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
def mock_config_item(mocker):
    return mocker.MagicMock(spec=PluginConfig)


@pytest.fixture
def mock_transaction(mocker):
    return mocker.MagicMock(spec=TransactionAPI)


@pytest.fixture(scope="session")
def networks_connected_to_tester():
    with ape.networks.parse_network_choice("::test"):
        yield ape.networks


@pytest.fixture(scope="session")
def ethereum(networks_connected_to_tester):
    return networks_connected_to_tester.ethereum


@pytest.fixture(scope="session")
def eth_tester_provider(networks_connected_to_tester):
    yield networks_connected_to_tester.active_provider


@pytest.fixture(scope="session")
def test_accounts(accounts):
    return accounts.test_accounts


@pytest.fixture
def sender(test_accounts):
    return test_accounts[0]


@pytest.fixture
def receiver(test_accounts):
    return test_accounts[1]


@pytest.fixture(scope="session")
def owner(test_accounts):
    return test_accounts[2]


@pytest.fixture
def solidity_contract_type() -> ContractType:
    return ContractType.parse_obj(RAW_SOLIDITY_CONTRACT_TYPE)


@pytest.fixture
def solidity_contract_container(solidity_contract_type) -> ContractContainer:
    return ContractContainer(contract_type=solidity_contract_type)


@pytest.fixture
def solidity_contract_instance(
    owner, solidity_contract_container, networks_connected_to_tester
) -> ContractInstance:
    return owner.deploy(solidity_contract_container)


@pytest.fixture
def vyper_contract_type() -> ContractType:
    return ContractType.parse_obj(RAW_VYPER_CONTRACT_TYPE)


@pytest.fixture
def vyper_contract_container(vyper_contract_type) -> ContractContainer:
    return ContractContainer(contract_type=vyper_contract_type)


@pytest.fixture
def vyper_contract_instance(
    owner, vyper_contract_container, networks_connected_to_tester
) -> ContractInstance:
    return owner.deploy(vyper_contract_container)


@pytest.fixture(params=("solidity", "vyper"))
def contract_container(
    request, solidity_contract_container, vyper_contract_container, networks_connected_to_tester
):
    return solidity_contract_container if request.param == "solidity" else vyper_contract_container


@pytest.fixture(params=("solidity", "vyper"))
def contract_instance(request, solidity_contract_instance, vyper_contract_instance):
    return solidity_contract_instance if request.param == "solidity" else vyper_contract_instance


@pytest.fixture(scope="session")
def temp_config(config):
    @contextmanager
    def func(data: Dict):
        with tempfile.TemporaryDirectory() as temp_dir_str:
            temp_dir = Path(temp_dir_str)
            config._cached_configs = {}
            config_file = temp_dir / CONFIG_FILE_NAME
            config_file.touch()
            config_file.write_text(yaml.dump(data))
            config.load(force_reload=True)

            with config.using_project(temp_dir):
                yield

            config_file.unlink()
            config._cached_configs = {}

    return func


@pytest.fixture
def project_with_contract(config):
    project_source_dir = APE_PROJECT_FOLDER
    project_dest_dir = config.PROJECT_FOLDER / project_source_dir.name
    copy_tree(project_source_dir.as_posix(), project_dest_dir.as_posix())

    with config.using_project(project_dest_dir) as project:
        yield project


@pytest.fixture
def clean_contracts_cache(chain):
    original_cached_contracts = chain.contracts._local_contracts
    chain.contracts._local_contracts = {}
    yield
    chain.contracts._local_contracts = original_cached_contracts


@pytest.fixture
def dependency_config(temp_config):
    dependencies_config = {
        "dependencies": [
            {
                "local": str(PROJECT_WITH_LONG_CONTRACTS_FOLDER),
                "name": "testdependency",
                "contracts_folder": "source/v0.1",
            }
        ]
    }
    with temp_config(dependencies_config):
        yield


@pytest.fixture
def base_projects_directory():
    return BASE_PROJECTS_DIRECTORY


@pytest.fixture
def assert_log_values(owner, chain, contract_instance):
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
    if chain.contracts._deployments_mapping_cache.exists():
        chain.contracts._deployments_mapping_cache.unlink()

    yield

    if chain.contracts._deployments_mapping_cache.exists():
        chain.contracts._deployments_mapping_cache.unlink()
