import pytest
from ethpm_types import ContractType

from ape import Contract
from ape.contracts import ContractInstance
from ape.exceptions import ContractNotFoundError, ConversionError
from ape_ethereum.proxies import _make_minimal_proxy
from tests.conftest import explorer_test, skip_if_plugin_installed


@pytest.fixture
def contract_0(vyper_contract_container):
    return vyper_contract_container


@pytest.fixture
def contract_1(solidity_contract_container):
    return solidity_contract_container


def test_instance_at(chain, contract_instance):
    contract = chain.contracts.instance_at(str(contract_instance.address))
    assert contract.contract_type == contract_instance.contract_type


def test_instance_at_unknown_hex_str(chain, contract_instance):
    # Fails when decoding Ethereum address and NOT conversion error.
    hex_str = "0x1402b10CA274cD76C441e16C844223F79D3566De12bb12b0aebFE41aDFAe302"
    with pytest.raises(ValueError, match=f"Unknown address value '{hex_str}'."):
        chain.contracts.instance_at(hex_str)


def test_instance_at_when_given_contract_type(chain, contract_instance):
    contract = chain.contracts.instance_at(
        str(contract_instance.address), contract_type=contract_instance.contract_type
    )
    assert contract.contract_type == contract_instance.contract_type


def test_instance_at_when_given_name_as_contract_type(chain, contract_instance):
    expected_match = "Expected type 'ContractType' for argument 'contract_type'."
    with pytest.raises(TypeError, match=expected_match):
        address = str(contract_instance.address)
        bad_contract_type = contract_instance.contract_type.name
        chain.contracts.instance_at(address, contract_type=bad_contract_type)


@explorer_test
def test_instance_at_uses_given_contract_type_when_retrieval_fails(mocker, chain, ape_caplog):
    # The manager always attempts retrieval so that default contact types can
    # get cached. However, sometimes an explorer plugin may fail. If given a contract-type
    # in that situation, we can use it and not fail and log the error instead.
    expected_contract_type = ContractType(contractName="foo", sourceId="foo.bar")
    new_address = "0x4a986a6dCA6dbf99bC3d17F8D71aFb0d60e740f8"
    expected_fail_message = "LOOK_FOR_THIS_FAIL_MESSAGE"
    existing_fn = chain.contracts.get

    def fn(addr, default=None):
        if addr == new_address:
            raise ValueError(expected_fail_message)

        return existing_fn(addr, default=default)

    original_get = chain.contracts.get
    mock_get = mocker.MagicMock()
    mock_get.side_effect = fn
    chain.contracts.get = mock_get
    try:
        actual = chain.contracts.instance_at(new_address, contract_type=expected_contract_type)
    finally:
        chain.contracts.get = original_get

    ape_caplog.assert_last_log(expected_fail_message)
    assert actual.contract_type == expected_contract_type


@explorer_test
def test_instance_at_contract_type_not_found_local_network(chain, eth_tester_provider):
    eth_tester_provider.network.__dict__["explorer"] = None
    new_address = "0x4a986a6dca6dbF99Bc3D17F8d71aFB0D60E740F9"
    expected = rf"Failed to get contract type for address '{new_address}'."
    with pytest.raises(ContractNotFoundError, match=expected):
        chain.contracts.instance_at(new_address)


@explorer_test
def test_instance_at_contract_type_not_found_live_network(chain, eth_tester_provider):
    eth_tester_provider.network.__dict__["explorer"] = None
    real_name = eth_tester_provider.network.name
    eth_tester_provider.network.name = "sepolia"
    try:
        new_address = "0x4a986a6dca6dbF99Bc3D17F8d71aFB0D60E740F9"
        expected = (
            rf"Failed to get contract type for address '{new_address}'. "
            r"Current network 'ethereum:sepolia:test' has no associated explorer plugin. "
            "Try installing an explorer plugin using .*ape plugins install etherscan.*, "
            r"or using a network with explorer support\."
        )
        with pytest.raises(ContractNotFoundError, match=expected):
            chain.contracts.instance_at(new_address)

    finally:
        eth_tester_provider.network.name = real_name


def test_instance_at_use_abi(chain, solidity_fallback_contract, owner):
    new_instance = owner.deploy(solidity_fallback_contract.contract_type)
    del chain.contracts[new_instance.address]
    with pytest.raises(ContractNotFoundError):
        _ = chain.contracts.instance_at(new_instance.address)

    # Now, use only ABI and ensure it works and caches!
    abi = solidity_fallback_contract.contract_type.abi
    instance = chain.contracts.instance_at(new_instance.address, abi=abi)
    assert instance.contract_type.abi

    # `abi=` not needed this time.
    instance2 = chain.contracts.instance_at(new_instance.address)
    assert instance2.contract_type.abi == instance.contract_type.abi


def test_cache_deployment_live_network(
    chain,
    vyper_contract_instance,
    vyper_contract_container,
    remove_disk_writes_deployments,
    dummy_live_network,
):
    # Arrange - Ensure the contract is not cached anywhere
    address = vyper_contract_instance.address
    contract_name = vyper_contract_instance.contract_type.name
    deployments = chain.contracts._deployments
    contract_types = chain.contracts._local_contract_types
    chain.contracts._local_contract_types = {
        a: ct for a, ct in contract_types.items() if a != address
    }
    chain.contracts._deployments = {n: d for n, d in deployments.items() if n != contract_name}

    # Act
    chain.contracts.cache_deployment(vyper_contract_instance)

    # Assert
    actual_deployments = chain.contracts.get_deployments(vyper_contract_container)
    actual_contract_type = chain.contracts._get_contract_type_from_disk(address)
    expected = vyper_contract_instance.contract_type
    assert len(actual_deployments) == 1
    assert actual_deployments[0].address == address
    assert actual_deployments[0].txn_hash == vyper_contract_instance.txn_hash
    assert chain.contracts.get(address) == expected
    assert actual_contract_type == expected


def test_cache_default_contract_type_when_used(solidity_contract_instance, chain, config):
    address = solidity_contract_instance.address
    contract_type = solidity_contract_instance.contract_type

    # Delete contract from local cache if it's there
    if address in chain.contracts._local_contract_types:
        del chain.contracts._local_contract_types[address]

    # Delete cache file if it exists
    cache_file = chain.contracts._contract_types_cache / f"{address}.json"
    if cache_file.is_file():
        cache_file.unlink()

    # Create a contract using the contract type when nothing is cached.
    contract = Contract(address, contract_type=contract_type)
    assert isinstance(contract, ContractInstance)

    # Ensure we don't need the contract type when creating it the second time.
    contract = Contract(address)
    assert isinstance(contract, ContractInstance)


@explorer_test
def test_contracts_getitem_contract_not_found(chain, eth_tester_provider):
    eth_tester_provider.network.__dict__["explorer"] = None
    new_address = "0x4a986a6dca6dbF99Bc3D17F8d71aFB0D60E740F9"
    real_name = eth_tester_provider.network.name
    eth_tester_provider.network.name = "sepolia"
    try:
        expected = (
            rf"Failed to get contract type for address '{new_address}'. "
            r"Current network 'ethereum:sepolia:test' has no associated explorer plugin. "
            "Try installing an explorer plugin using .*ape plugins install etherscan.*, "
            r"or using a network with explorer support\."
        )
        with pytest.raises(KeyError, match=expected):
            _ = chain.contracts[new_address]

    finally:
        eth_tester_provider.network.name = real_name


def test_deployments_mapping_cache_location(chain):
    # Arrange / Act
    mapping_location = chain.contracts._deployments_mapping_cache
    split_mapping_location = str(mapping_location).split("/")

    # Assert
    assert split_mapping_location[-1] == "deployments_map.json"
    assert split_mapping_location[-2] == "ethereum"


def test_deployments_when_offline(chain, networks_disconnected, vyper_contract_container):
    """
    Ensure you don't get `ProviderNotConnectedError` here.
    """
    assert chain.contracts.get_deployments(vyper_contract_container) == []


def test_get_deployments_local(chain, owner, contract_0, contract_1):
    # Arrange
    chain.contracts._local_deployments_mapping = {}
    chain.contracts._local_contract_types = {}
    starting_contracts_list_0 = chain.contracts.get_deployments(contract_0)
    starting_contracts_list_1 = chain.contracts.get_deployments(contract_1)
    deployed_contract_0 = owner.deploy(contract_0, 900000000)
    deployed_contract_1 = owner.deploy(contract_1, 900000001)

    # Act
    contracts_list_0 = chain.contracts.get_deployments(contract_0)
    contracts_list_1 = chain.contracts.get_deployments(contract_1)

    # Assert
    for contract_list in (contracts_list_0, contracts_list_1):
        assert type(contract_list[0]) is ContractInstance

    index_0 = len(contracts_list_0) - len(starting_contracts_list_0) - 1
    index_1 = len(contracts_list_1) - len(starting_contracts_list_1) - 1
    actual_address_0 = contracts_list_0[index_0].address
    assert actual_address_0 == deployed_contract_0.address
    actual_address_1 = contracts_list_1[index_1].address
    assert actual_address_1 == deployed_contract_1.address


def test_get_deployments_live(
    chain, owner, contract_0, contract_1, remove_disk_writes_deployments, dummy_live_network
):
    deployed_contract_0 = owner.deploy(contract_0, 8000000, required_confirmations=0)
    deployed_contract_1 = owner.deploy(contract_1, 8000001, required_confirmations=0)

    # Act
    my_contracts_list_0 = chain.contracts.get_deployments(contract_0)
    my_contracts_list_1 = chain.contracts.get_deployments(contract_1)

    # Assert
    address_from_api_0 = my_contracts_list_0[-1].address
    assert address_from_api_0 == deployed_contract_0.address
    address_from_api_1 = my_contracts_list_1[-1].address
    assert address_from_api_1 == deployed_contract_1.address


def test_get_multiple_deployments_live(
    chain, owner, contract_0, contract_1, remove_disk_writes_deployments, dummy_live_network
):
    starting_contracts_list_0 = chain.contracts.get_deployments(contract_0)
    starting_contracts_list_1 = chain.contracts.get_deployments(contract_1)
    initial_deployed_contract_0 = owner.deploy(contract_0, 700000, required_confirmations=0)
    initial_deployed_contract_1 = owner.deploy(contract_1, 700001, required_confirmations=0)
    owner.deploy(contract_0, 700002, required_confirmations=0)
    owner.deploy(contract_1, 700003, required_confirmations=0)
    final_deployed_contract_0 = owner.deploy(contract_0, 600000, required_confirmations=0)
    final_deployed_contract_1 = owner.deploy(contract_1, 600001, required_confirmations=0)
    contracts_list_0 = chain.contracts.get_deployments(contract_0)
    contracts_list_1 = chain.contracts.get_deployments(contract_1)
    contract_type_map = {
        "ApeContract0": (initial_deployed_contract_0, final_deployed_contract_0),
        "ApeContract1": (initial_deployed_contract_1, final_deployed_contract_1),
    }

    assert len(contracts_list_0) == len(starting_contracts_list_0) + 3
    assert len(contracts_list_1) == len(starting_contracts_list_1) + 3

    for ct_name, ls in zip(("ApeContract0", "ApeContract1"), (contracts_list_0, contracts_list_1)):
        initial_ct, final_ct = contract_type_map[ct_name]
        assert ls[len(ls) - 3].address == initial_ct.address
        assert ls[-1].address == final_ct.address


def test_cache_updates_per_deploy(owner, chain, contract_0, contract_1):
    # Arrange / Act
    initial_contracts = chain.contracts.get_deployments(contract_0)
    expected_first_contract = owner.deploy(contract_0, 6787678)

    owner.deploy(contract_0, 6787679)
    owner.deploy(contract_0, 6787680)
    expected_last_contract = owner.deploy(contract_0, 6787681)

    actual_contracts = chain.contracts.get_deployments(contract_0)
    first_index = len(initial_contracts)  # next index before deploys from this test
    actual_first_contract = actual_contracts[first_index].address
    actual_last_contract = actual_contracts[-1].address

    # Assert
    fail_msg = f"Check deployments: {', '.join([c.address for c in actual_contracts])}"
    assert len(actual_contracts) - len(initial_contracts) == 4, fail_msg
    assert actual_first_contract == expected_first_contract.address, fail_msg
    assert actual_last_contract == expected_last_contract.address, fail_msg


def test_get_multiple(vyper_contract_instance, solidity_contract_instance, chain):
    contract_map = chain.contracts.get_multiple(
        (vyper_contract_instance.address, solidity_contract_instance.address)
    )
    assert len(contract_map) == 2
    assert contract_map[vyper_contract_instance.address] == vyper_contract_instance.contract_type
    assert (
        contract_map[solidity_contract_instance.address] == solidity_contract_instance.contract_type
    )


def test_get_multiple_no_addresses(chain, caplog):
    contract_map = chain.contracts.get_multiple([])
    assert not contract_map
    assert "WARNING" in caplog.records[-1].levelname
    assert "No addresses provided." in caplog.messages[-1]


def test_get_multiple_include_non_contract_address(vyper_contract_instance, chain, owner):
    actual = chain.contracts.get_multiple((vyper_contract_instance.address, owner.address))
    assert len(actual) == 1
    assert actual[vyper_contract_instance.address] == vyper_contract_instance.contract_type


@skip_if_plugin_installed("ens")
def test_get_multiple_attempts_to_convert(chain):
    with pytest.raises(ConversionError):
        chain.contracts.get_multiple(("test.eth",))


def test_get_non_contract_address(chain, owner):
    actual = chain.contracts.get(owner.address)
    assert actual is None


def test_get_attempts_to_convert(chain):
    with pytest.raises(ConversionError):
        # NOTE: using eth2 suffix so still works if ape-ens is installed.
        chain.contracts.get("test.eth2")


@explorer_test
def test_get_attempts_explorer(
    mock_explorer, create_mock_sepolia, chain, owner, vyper_fallback_container
):
    contract = owner.deploy(vyper_fallback_container)

    def get_contract_type(addr):
        if addr == contract.address:
            return contract.contract_type

        raise ValueError("nope")

    # Hack in a way to publish on this local network.
    with create_mock_sepolia() as network:
        mock_explorer.get_contract_type.side_effect = get_contract_type
        network.__dict__["explorer"] = mock_explorer
        del chain.contracts[contract.address]
        try:
            actual = chain.contracts.get(contract.address)
        finally:
            network.__dict__["explorer"] = None

        assert actual == contract.contract_type
        assert mock_explorer.get_contract_type.call_count > 0
        mock_explorer.get_contract_type.reset_mock()


@explorer_test
def test_get_attempts_explorer_logs_errors_from_explorer(
    mock_explorer, create_mock_sepolia, chain, owner, vyper_fallback_container, ape_caplog
):
    contract = owner.deploy(vyper_fallback_container)
    check_error_str = "__CHECK_FOR_THIS_ERROR__"

    def get_contract_type(addr):
        if addr == contract.address:
            raise ValueError(check_error_str)

        raise ValueError("nope")

    with create_mock_sepolia() as network:
        mock_explorer.get_contract_type.side_effect = get_contract_type
        network.__dict__["explorer"] = mock_explorer
        expected_log = (
            f"Attempted to retrieve contract type from explorer 'mock' "
            f"from address '{contract.address}' but encountered an "
            f"exception: {check_error_str}"
        )
        del chain.contracts[contract.address]
        try:
            actual = chain.contracts.get(contract.address)
        finally:
            network.__dict__["explorer"] = None

        assert expected_log in ape_caplog.head
        assert actual is None
        mock_explorer.get_contract_type.reset_mock()


@explorer_test
def test_get_attempts_explorer_logs_rate_limit_error_from_explorer(
    mock_explorer, create_mock_sepolia, chain, owner, vyper_fallback_container, ape_caplog
):
    contract = owner.deploy(vyper_fallback_container)

    # Ensure is not cached locally.
    del chain.contracts[contract.address]

    check_error_str = "you have been rate limited"

    def get_contract_type(addr):
        if addr == contract.address:
            raise ValueError(check_error_str)

        raise ValueError("nope")

    with create_mock_sepolia() as network:
        mock_explorer.get_contract_type.side_effect = get_contract_type
        network.__dict__["explorer"] = mock_explorer

        # For rate limit errors, we don't show anything else,
        # as it may be confusing.
        expected_log = "you have been rate limited"
        try:
            actual = chain.contracts.get(contract.address)
        finally:
            network.__dict__["explorer"] = None

        assert expected_log in ape_caplog.head
        assert actual is None
        mock_explorer.get_contract_type.reset_mock()


def test_cache_non_checksum_address(chain, vyper_contract_instance):
    """
    When caching a non-checksum address, it should use its checksum
    form automatically.
    """
    if vyper_contract_instance.address in chain.contracts:
        del chain.contracts[vyper_contract_instance.address]

    lowered_address = vyper_contract_instance.address.lower()
    chain.contracts[lowered_address] = vyper_contract_instance.contract_type
    assert chain.contracts[vyper_contract_instance.address] == vyper_contract_instance.contract_type


def test_get_creation_metadata(chain, vyper_contract_instance, owner):
    address = vyper_contract_instance.address
    creation = chain.contracts.get_creation_metadata(address)
    assert creation.deployer == owner.address

    chain.mine()
    creation = chain.contracts.get_creation_metadata(address)
    assert creation.deployer == owner.address


def test_delete_contract(vyper_contract_instance, chain):
    # Ensure we start with it cached.
    if vyper_contract_instance.address not in chain.contracts:
        chain.contracts[vyper_contract_instance.address] = vyper_contract_instance

    del chain.contracts[vyper_contract_instance.address]
    assert vyper_contract_instance.address not in chain.contracts

    # Ensure we can't access it.
    with pytest.raises(KeyError):
        _ = chain.contracts[vyper_contract_instance.address]


def test_delete_proxy(vyper_contract_instance, chain, ethereum, owner):
    address = vyper_contract_instance.address
    container = _make_minimal_proxy(address=address.lower())
    proxy = container.deploy(sender=owner)

    # Ensure we start with both the proxy and the target contracts cached.
    if proxy.address not in chain.contracts:
        chain.contracts[proxy.address] = proxy

    proxy_info = ethereum.get_proxy_info(proxy.address)
    chain.contracts.cache_proxy_info(proxy.address, proxy_info)
    if proxy_info.target not in chain.contracts:
        chain.contracts[proxy_info.target] = vyper_contract_instance

    del chain.contracts[proxy.address]
    assert proxy.address not in chain.contracts

    # Ensure we can't access it.
    with pytest.raises(KeyError):
        _ = chain.contracts[proxy.address]

    # Ensure we can't access the target either.
    with pytest.raises(KeyError):
        _ = chain.contracts[proxy_info.target]


def test_clear_local_caches(chain, vyper_contract_instance, proxy_contract_container, owner):
    # Ensure contract type exists.
    address = vyper_contract_instance.address
    # Ensure blueprint exists.
    chain.contracts._local_blueprints[address] = vyper_contract_instance.contract_type
    # Ensure proxy exists.
    proxy = proxy_contract_container.deploy(address, sender=owner)
    # Ensure creation exists.
    _ = chain.contracts.get_creation_metadata(address)

    # Test setup verification.
    assert (
        address in chain.contracts._local_contract_types
    ), "Setup failed - no contract type(s) cached"
    assert proxy.address in chain.contracts._local_proxies, "Setup failed - no proxy cached"
    assert (
        address in chain.contracts._local_contract_creation
    ), "Setup failed - no creation(s) cached"

    # This is the method we are testing.
    chain.contracts.clear_local_caches()

    # Assertions - everything should be empty.
    assert chain.contracts._local_proxies == {}
    assert chain.contracts._local_blueprints == {}
    assert chain.contracts._local_deployments_mapping == {}
    assert chain.contracts._local_contract_creation == {}
