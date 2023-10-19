import pytest
from ethpm_types import ContractType

from ape import Contract
from ape.contracts import ContractInstance
from ape.exceptions import ContractNotFoundError, ConversionError
from ape_ethereum.proxies import _make_minimal_proxy
from tests.conftest import explorer_test, skip_if_plugin_installed


@pytest.fixture
def contract_0(project_with_contract):
    return project_with_contract.ApeContract0


@pytest.fixture
def contract_1(project_with_contract):
    return project_with_contract.ApeContract1


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

    chain.contracts.get = mocker.MagicMock()
    chain.contracts.get.side_effect = fn

    actual = chain.contracts.instance_at(new_address, contract_type=expected_contract_type)
    ape_caplog.assert_last_log(expected_fail_message)
    assert actual.contract_type == expected_contract_type


@explorer_test
def test_instance_at_contract_type_not_found(chain, eth_tester_provider):
    eth_tester_provider.network.__dict__["explorer"] = None
    new_address = "0x4a986a6dca6dbF99Bc3D17F8d71aFB0D60E740F9"
    expected = (
        rf"Failed to get contract type for address '{new_address}'. "
        r"Current provider 'ethereum:local:test' has no associated explorer plugin. "
        "Try installing an explorer plugin using .*ape plugins install etherscan.*, "
        r"or using a network with explorer support\."
    )
    with pytest.raises(ContractNotFoundError, match=expected):
        chain.contracts.instance_at(new_address)


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
    expected = (
        rf"Failed to get contract type for address '{new_address}'. "
        r"Current provider 'ethereum:local:test' has no associated explorer plugin. "
        "Try installing an explorer plugin using .*ape plugins install etherscan.*, "
        r"or using a network with explorer support\."
    )
    with pytest.raises(IndexError, match=expected):
        _ = chain.contracts[new_address]


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
    deployed_contract_0 = owner.deploy(contract_0)
    deployed_contract_1 = owner.deploy(contract_1)

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
    deployed_contract_0 = owner.deploy(contract_0, required_confirmations=0)
    deployed_contract_1 = owner.deploy(contract_1, required_confirmations=0)

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
    initial_deployed_contract_0 = owner.deploy(contract_0, required_confirmations=0)
    initial_deployed_contract_1 = owner.deploy(contract_1, required_confirmations=0)
    owner.deploy(contract_0, required_confirmations=0)
    owner.deploy(contract_1, required_confirmations=0)
    final_deployed_contract_0 = owner.deploy(contract_0, required_confirmations=0)
    final_deployed_contract_1 = owner.deploy(contract_1, required_confirmations=0)
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
    expected_first_contract = owner.deploy(contract_0)

    owner.deploy(contract_0)
    owner.deploy(contract_0)
    expected_last_contract = owner.deploy(contract_0)

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


def test_get_all_include_non_contract_address(vyper_contract_instance, chain, owner):
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
        chain.contracts.get("test.eth")


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


def test_get_contract_receipt(chain, vyper_contract_instance):
    address = vyper_contract_instance.address
    receipt = chain.contracts.get_creation_receipt(address)
    assert receipt.contract_address == address

    chain.mine()
    receipt = chain.contracts.get_creation_receipt(address)
    assert receipt.contract_address == address


def test_delete_contract(vyper_contract_instance, chain):
    # Ensure we start with it cached.
    if vyper_contract_instance.address not in chain.contracts:
        chain.contracts[vyper_contract_instance.address] = vyper_contract_instance

    del chain.contracts[vyper_contract_instance.address]
    assert vyper_contract_instance.address not in chain.contracts

    # Ensure we can't access it.
    with pytest.raises(IndexError):
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
    with pytest.raises(IndexError):
        _ = chain.contracts[proxy.address]

    # Ensure we can't access the target either.
    with pytest.raises(IndexError):
        _ = chain.contracts[proxy_info.target]
