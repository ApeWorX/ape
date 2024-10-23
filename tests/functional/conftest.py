import threading
import time
from contextlib import contextmanager
from pathlib import Path
from shutil import copytree
from typing import Optional, cast

import pytest
from eth_pydantic_types import HexBytes
from eth_utils import to_hex
from ethpm_types import ContractType, ErrorABI, MethodABI
from ethpm_types.abi import ABIType

import ape
from ape.contracts import ContractContainer, ContractInstance
from ape.contracts.base import ContractCallHandler
from ape.exceptions import ChainError, ContractLogicError, ProviderError
from ape.logging import LogLevel
from ape.logging import logger as _logger
from ape.types.address import AddressType
from ape.types.events import ContractLog
from ape.utils.misc import LOCAL_NETWORK_NAME
from ape_ethereum.proxies import minimal_proxy as _minimal_proxy_container

ALIAS_2 = "__FUNCTIONAL_TESTS_ALIAS_2__"
TEST_ADDRESS = cast(AddressType, "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045")
BASE_PROJECTS_DIRECTORY = (Path(__file__).parent / "data" / "projects").absolute()
PROJECT_WITH_LONG_CONTRACTS_FOLDER = BASE_PROJECTS_DIRECTORY / "LongContractsFolder"
APE_PROJECT_FOLDER = BASE_PROJECTS_DIRECTORY / "ApeProject"
BASE_SOURCES_DIRECTORY = (Path(__file__).parent / "data/sources").absolute()

CALL_WITH_STRUCT_INPUT = MethodABI.model_validate(
    {
        "type": "function",
        "name": "getTradeableOrderWithSignature",
        "stateMutability": "view",
        "inputs": [
            {"name": "owner", "type": "address", "internalType": "address"},
            {
                "name": "params",
                "type": "tuple",
                "components": [
                    {
                        "name": "handler",
                        "type": "address",
                        "internalType": "contract IConditionalOrder",
                    },
                    {"name": "salt", "type": "bytes32", "internalType": "bytes32"},
                    {"name": "staticInput", "type": "bytes", "internalType": "bytes"},
                ],
                "internalType": "struct IConditionalOrder.ConditionalOrderParams",
            },
            {"name": "offchainInput", "type": "bytes", "internalType": "bytes"},
            {"name": "proof", "type": "bytes32[]", "internalType": "bytes32[]"},
        ],
        "outputs": [
            {
                "name": "order",
                "type": "tuple",
                "components": [
                    {"name": "sellToken", "type": "address", "internalType": "contract IERC20"},
                    {"name": "buyToken", "type": "address", "internalType": "contract IERC20"},
                    {"name": "receiver", "type": "address", "internalType": "address"},
                    {"name": "sellAmount", "type": "uint256", "internalType": "uint256"},
                    {"name": "buyAmount", "type": "uint256", "internalType": "uint256"},
                    {"name": "validTo", "type": "uint32", "internalType": "uint32"},
                    {"name": "appData", "type": "bytes32", "internalType": "bytes32"},
                    {"name": "feeAmount", "type": "uint256", "internalType": "uint256"},
                    {"name": "kind", "type": "bytes32", "internalType": "bytes32"},
                    {"name": "partiallyFillable", "type": "bool", "internalType": "bool"},
                    {"name": "sellTokenBalance", "type": "bytes32", "internalType": "bytes32"},
                    {"name": "buyTokenBalance", "type": "bytes32", "internalType": "bytes32"},
                ],
                "internalType": "struct GPv2Order.Data",
            },
            {"name": "signature", "type": "bytes", "internalType": "bytes"},
        ],
    }
)
METHOD_WITH_STRUCT_INPUT = MethodABI.model_validate(
    {
        "type": "function",
        "name": "getTradeableOrderWithSignature",
        "stateMutability": "view",
        "inputs": [
            {"name": "owner", "type": "address", "internalType": "address"},
            {
                "name": "params",
                "type": "tuple",
                "components": [
                    {
                        "name": "handler",
                        "type": "address",
                        "internalType": "contract IConditionalOrder",
                    },
                    {"name": "salt", "type": "bytes32", "internalType": "bytes32"},
                    {"name": "staticInput", "type": "bytes", "internalType": "bytes"},
                ],
                "internalType": "struct IConditionalOrder.ConditionalOrderParams",
            },
            {"name": "offchainInput", "type": "bytes", "internalType": "bytes"},
            {"name": "proof", "type": "bytes32[]", "internalType": "bytes32[]"},
        ],
        "outputs": [
            {
                "name": "order",
                "type": "tuple",
                "components": [
                    {"name": "sellToken", "type": "address", "internalType": "contract IERC20"},
                    {"name": "buyToken", "type": "address", "internalType": "contract IERC20"},
                    {"name": "receiver", "type": "address", "internalType": "address"},
                    {"name": "sellAmount", "type": "uint256", "internalType": "uint256"},
                    {"name": "buyAmount", "type": "uint256", "internalType": "uint256"},
                    {"name": "validTo", "type": "uint32", "internalType": "uint32"},
                    {"name": "appData", "type": "bytes32", "internalType": "bytes32"},
                    {"name": "feeAmount", "type": "uint256", "internalType": "uint256"},
                    {"name": "kind", "type": "bytes32", "internalType": "bytes32"},
                    {"name": "partiallyFillable", "type": "bool", "internalType": "bool"},
                    {"name": "sellTokenBalance", "type": "bytes32", "internalType": "bytes32"},
                    {"name": "buyTokenBalance", "type": "bytes32", "internalType": "bytes32"},
                ],
                "internalType": "struct GPv2Order.Data",
            },
            {"name": "signature", "type": "bytes", "internalType": "bytes"},
        ],
    }
)


class _ContractLogicError(ContractLogicError):
    pass


@pytest.hookimpl(trylast=True, hookwrapper=True)
def pytest_collection_finish(session):
    with ape.networks.parse_network_choice("::test"):
        # Sets the active provider
        yield


@pytest.fixture
def mock_web3(mocker):
    return mocker.MagicMock()


@pytest.fixture
def mock_transaction(mocker):
    tx = mocker.MagicMock()
    tx.required_confirmations = 0
    return tx


@pytest.fixture(scope="session")
def address():
    return TEST_ADDRESS


@pytest.fixture
def second_keyfile_account(sender, keyparams, temp_keyfile_account_ctx):
    with temp_keyfile_account_ctx(ALIAS_2, keyparams, sender) as account:
        # Ensure starts off locked.
        account.lock()
        yield account


@pytest.fixture
def solidity_contract_instance(
    owner, solidity_contract_container, networks_connected_to_tester
) -> ContractInstance:
    return owner.deploy(solidity_contract_container, 0)


@pytest.fixture(scope="session")
def solidity_fallback_contract_type(get_contract_type) -> ContractType:
    return get_contract_type("SolFallbackAndReceive")


@pytest.fixture(scope="session")
def vyper_fallback_contract_type(get_contract_type) -> ContractType:
    return get_contract_type("VyDefault")


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
    return get_contract_type("RevertsContract")


@pytest.fixture(scope="session")
def sub_reverts_contract_type(get_contract_type) -> ContractType:
    return get_contract_type("SubReverts")


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
    contract_type = get_contract_type("DsNoteTest")
    contract_container = ContractContainer(contract_type=contract_type)
    return contract_container.deploy(sender=owner)


@pytest.fixture(scope="session")
def project_with_contract():
    with ape.Project(APE_PROJECT_FOLDER).isolate_in_tempdir() as project:
        yield project


@pytest.fixture(scope="session")
def project_with_source_files_contract(project_with_contract):
    bases_source_dir = BASE_SOURCES_DIRECTORY
    project_source_dir = project_with_contract.path

    with ape.Project.create_temporary_project() as tmp_project:
        copytree(project_source_dir, str(tmp_project.path), dirs_exist_ok=True)
        copytree(bases_source_dir, tmp_project.path / "contracts", dirs_exist_ok=True)
        yield tmp_project


@pytest.fixture
def clean_contracts_cache(chain):
    original_cached_contracts = chain.contracts._local_contract_types
    chain.contracts._local_contract_types = {}
    yield
    chain.contracts._local_contract_types = original_cached_contracts


@pytest.fixture
def project_with_dependency_config(project):
    dependencies_config = {
        "contracts_folder": "functional/data/contracts/local",
        "dependencies": [
            {
                "local": str(PROJECT_WITH_LONG_CONTRACTS_FOLDER),
                "name": "testdependency",
                "config_override": {
                    "contracts_folder": "source/v0.1",
                },
                "version": "releases/v6",  # Testing having a slash in version.
            }
        ],
    }
    project.clean()
    with project.isolate_in_tempdir(**dependencies_config) as tmp_project:
        yield tmp_project


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
        contract = ContractType.model_validate_json(path.read_text())
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
            except (ChainError, ProviderError):
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
        assert isinstance(log.b, bytes)
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
    original_network = chain.provider.network.name
    chain.provider.network.name = "sepolia"
    yield chain.provider.network
    chain.provider.network.name = original_network


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
    ct = get_contract_type("ContractC")
    return owner.deploy(ContractContainer(ct))


@pytest.fixture
def middle_contract(eth_tester_provider, owner, get_contract_type, leaf_contract):
    ct = get_contract_type("ContractB")
    return owner.deploy(ContractContainer(ct), leaf_contract)


@pytest.fixture
def contract_with_call_depth(
    owner, eth_tester_provider, get_contract_type, leaf_contract, middle_contract
):
    contract = ContractContainer(get_contract_type("ContractA"))
    return owner.deploy(contract, middle_contract, leaf_contract)


@pytest.fixture
def sub_reverts_contract_instance(owner, sub_reverts_contract_container, eth_tester_provider):
    return owner.deploy(sub_reverts_contract_container, required_confirmations=0)


@pytest.fixture(scope="session")
def error_contract_container(get_contract_type):
    ct = get_contract_type("HasError")
    return ContractContainer(ct)


@pytest.fixture
def error_contract(owner, error_contract_container, eth_tester_provider):
    _ = eth_tester_provider  # Ensure uses eth tester
    return owner.deploy(error_contract_container, 1)


@pytest.fixture
def vyper_factory(owner, get_contract_type):
    return owner.deploy(ContractContainer(get_contract_type("VyperFactory")))


@pytest.fixture
def vyper_printing(owner, get_contract_type):
    return owner.deploy(ContractContainer(get_contract_type("printing")))


@pytest.fixture
def vyper_blueprint(owner, vyper_contract_container):
    receipt = owner.declare(vyper_contract_container)
    return receipt.contract_address


@pytest.fixture
def minimal_proxy_container():
    return _minimal_proxy_container


@pytest.fixture
def minimal_proxy(owner, minimal_proxy_container):
    return owner.deploy(minimal_proxy_container)


@pytest.fixture
def mock_explorer(mocker):
    explorer = mocker.MagicMock()
    explorer.name = "mock"  # Needed for network data serialization.
    return explorer


@pytest.fixture
def call_abi_with_struct_input():
    return CALL_WITH_STRUCT_INPUT


@pytest.fixture
def fake_contract(mocker):
    # Only needed for initialization; never used.
    return mocker.MagicMock()


@pytest.fixture
def call_handler_with_struct_input(fake_contract, call_abi_with_struct_input):
    abi = call_abi_with_struct_input
    return ContractCallHandler(contract=fake_contract, abis=[abi])


@pytest.fixture(scope="session")
def struct_input_for_call(owner):
    return [owner, [owner, b"skip", b"skip"], b"skip", [b"skip"]]


@pytest.fixture(scope="session")
def output_from_struct_input_call(accounts):
    # Expected when using `struct_input_for_call`.
    addr = accounts[0].address.replace("0x", "")
    return HexBytes(
        f"0x26e0a196000000000000000000000000{addr}000000000000000000000000000000000"
        f"0000000000000000000000000000080000000000000000000000000000000000000000000"
        f"0000000000000000000120000000000000000000000000000000000000000000000000000"
        f"0000000000160000000000000000000000000{addr}736b69700000000000000000000000"
        f"0000000000000000000000000000000000000000000000000000000000000000000000000"
        f"0000000000000000000000060000000000000000000000000000000000000000000000000"
        f"0000000000000004736b69700000000000000000000000000000000000000000000000000"
        f"0000000000000000000000000000000000000000000000000000000000000000000000473"
        f"6b69700000000000000000000000000000000000000000000000000000000000000000000"
        f"00000000000000000000000000000000000000000000000000001736b6970000000000000"
        f"00000000000000000000000000000000000000000000"
    )


@pytest.fixture
def method_abi_with_struct_input():
    return METHOD_WITH_STRUCT_INPUT


@pytest.fixture
def mock_compiler(make_mock_compiler):
    return make_mock_compiler()


@pytest.fixture
def make_mock_compiler(mocker):
    def fn(name="mock"):
        mock = mocker.MagicMock()
        mock.name = "mock"
        mock.ext = f".__{name}__"
        mock.tracked_settings = []
        mock.ast = None
        mock.pcmap = None

        def mock_compile(paths, project=None, settings=None):
            settings = settings or {}
            mock.tracked_settings.append(settings)
            result = []
            for path in paths:
                if path.suffix == mock.ext:
                    name = path.stem
                    code = to_hex(123)
                    data = {
                        "contractName": name,
                        "abi": mock.abi,
                        "deploymentBytecode": code,
                        "sourceId": f"{project.contracts_folder.name}/{path.name}",
                    }
                    if ast := mock.ast:
                        data["ast"] = ast
                    if pcmap := mock.pcmap:
                        data["pcmap"] = pcmap

                    # Check for mocked overrides
                    overrides = mock.overrides
                    if isinstance(overrides, dict):
                        data = {**data, **overrides}

                    contract_type = ContractType.model_validate(data)
                    result.append(contract_type)

            return result

        mock.compile.side_effect = mock_compile
        return mock

    return fn


@pytest.fixture
def mock_sepolia(create_mock_sepolia):
    """
    Temporarily tricks Ape into thinking the local network
    is Sepolia so we can test features that require a live
    network.
    """
    with create_mock_sepolia() as network:
        yield network


@pytest.fixture
def create_mock_sepolia(ethereum, eth_tester_provider, vyper_contract_instance):
    @contextmanager
    def fn():
        # Ensuring contract exists before hack.
        # This allow the network to be past genesis which is more realistic.
        _ = vyper_contract_instance
        eth_tester_provider.network.name = "sepolia"
        yield eth_tester_provider.network
        eth_tester_provider.network.name = LOCAL_NETWORK_NAME

    return fn


@pytest.fixture
def disable_fork_providers(ethereum):
    """
    When ape-hardhat or ape-foundry is installed,
    this tricks the test into thinking they are not
    (only uses sepolia-fork).
    """
    actual = ethereum.sepolia_fork.__dict__.pop("providers", {})
    ethereum.sepolia_fork.__dict__["providers"] = {}
    yield
    if actual:
        ethereum.sepolia_fork.__dict__["providers"] = actual


@pytest.fixture
def mock_fork_provider(mocker, ethereum, mock_sepolia):
    """
    A fake provider representing something like ape-foundry
    that can fork networks (only uses sepolia-fork).
    """
    initial_providers = ethereum.sepolia_fork.__dict__.pop("providers", {})
    initial_default = ethereum.sepolia_fork._default_provider
    mock_provider = mocker.MagicMock()
    mock_provider.name = "mock"
    mock_provider.network = ethereum.sepolia_fork

    # Have to do this because providers are partials.
    def fake_partial(*args, **kwargs):
        mock_provider.partial_call = (args, kwargs)
        return mock_provider

    ethereum.sepolia_fork._default_provider = "mock"
    ethereum.sepolia_fork.__dict__["providers"] = {"mock": fake_partial}
    yield mock_provider
    if initial_providers:
        ethereum.sepolia_fork.__dict__["providers"] = initial_providers
    if initial_default:
        ethereum.sepolia_fork._default_provider = initial_default


@pytest.fixture
def delete_account_after():
    @contextmanager
    def delete_account_context(alias: str):
        yield
        account_path = ape.config.DATA_FOLDER / "accounts" / f"{alias}.json"
        if account_path.is_file():
            account_path.unlink()

    return delete_account_context


@pytest.fixture
def setup_custom_error(chain):
    def fn(addr: AddressType):
        abi = [
            ErrorABI(
                type="error",
                name="AllowanceExpired",
                inputs=[
                    ABIType(
                        name="deadline", type="uint256", components=None, internal_type="uint256"
                    )
                ],
            ),
            MethodABI(
                type="function",
                name="execute",
                stateMutability="payable",
                inputs=[
                    ABIType(name="commands", type="bytes", components=None, internal_type="bytes"),
                    ABIType(
                        name="inputs", type="bytes[]", components=None, internal_type="bytes[]"
                    ),
                ],
                outputs=[],
            ),
        ]
        contract_type = ContractType(abi=abi)

        # Hack in contract-type.
        chain.contracts._local_contract_types[addr] = contract_type

    return fn
