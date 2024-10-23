import copy
from pathlib import Path

import pytest

import ape
from ape.api.networks import EcosystemAPI
from ape.exceptions import NetworkError, ProviderNotFoundError
from ape.utils.misc import LOCAL_NETWORK_NAME
from ape.utils.testing import DEFAULT_TEST_CHAIN_ID


class NewChainID:
    chain_id = 12345678987654

    def __call__(self, *args, **kwargs) -> int:
        self.chain_id += 1
        return self.chain_id


chain_id_factory = NewChainID()

DEFAULT_CHOICES = {
    "::node",
    "::test",
    ":sepolia",
    ":sepolia:node",
    ":local",
    ":mainnet",
    ":mainnet:node",
    "ethereum",
    "ethereum::test",
    "ethereum::node",
    "ethereum:sepolia",
    "ethereum:sepolia:node",
    "ethereum:local",
    "ethereum:local:node",
    "ethereum:local:test",
    "ethereum:mainnet",
    "ethereum:mainnet:node",
}


@pytest.fixture
def get_provider_with_unused_chain_id(networks_connected_to_tester):
    networks = networks_connected_to_tester

    def fn(**more_settings):
        chain_id = chain_id_factory()
        settings = {"chain_id": chain_id, **more_settings}
        choice = "ethereum:local:test"
        disconnect_after = settings.pop("disconnect_after", True)
        context = networks.parse_network_choice(
            choice, disconnect_after=disconnect_after, provider_settings=settings
        )
        return context

    return fn


@pytest.fixture
def get_context(networks_connected_to_tester):
    def fn():
        return networks_connected_to_tester.parse_network_choice("ethereum:local:test")

    return fn


@pytest.fixture
def network_with_no_providers(ethereum):
    network = ethereum.get_network("sepolia-fork")
    default_provider = network.default_provider
    providers = network.__dict__["providers"]

    if default_provider or providers:
        # Handle user running tests with forked-network plugins installed
        network._default_provider = None
        network.__dict__["providers"] = []

    yield network

    if default_provider or providers:
        network._default_provider = default_provider.name
        network.__dict__["providers"] = providers
        assert network.default_provider, "Tear-down failed - providers not set."


def test_get_network_choices(networks, ethereum, mocker):
    # Simulate having a provider like foundry installed.
    mock_provider = mocker.MagicMock()
    mock_provider.name = "mock"
    ethereum.networks["mainnet-fork"].providers["mock"] = mock_provider
    ethereum.networks["local"].providers["mock"] = mock_provider

    # Ensure the provider shows up both mainnet fork and local
    # (There was once a bug where it was skipped!)
    expected = {":mainnet-fork:mock", ":local:mock"}

    actual = {c for c in networks.get_network_choices()}
    expected = DEFAULT_CHOICES.union(expected)
    assert expected.issubset(actual)


def test_get_network_choices_filter_ecosystem(networks):
    actual = {c for c in networks.get_network_choices(ecosystem_filter="ethereum")}
    assert DEFAULT_CHOICES.issubset(actual)


def test_get_network_choices_filter_network(networks):
    actual = {c for c in networks.get_network_choices(network_filter="mainnet")}
    mainnet_choices = {
        ":mainnet",
        ":mainnet:node",
        "ethereum",
        "ethereum:mainnet",
        "ethereum:mainnet:node",
    }
    assert mainnet_choices.issubset(actual)


def test_get_network_choices_filter_provider(networks):
    actual = {c for c in networks.get_network_choices(provider_filter="test")}
    expected = {"::test", ":local", "ethereum:local", "ethereum:local:test", "ethereum"}
    assert all(e in actual for e in expected)


def test_get_provider_when_no_default(network_with_no_providers):
    expected = f"No default provider for network '{network_with_no_providers.name}'"
    with pytest.raises(NetworkError, match=expected):
        # Not provider installed out-of-the-box for sepolia-fork network
        provider = network_with_no_providers.get_provider()
        assert not provider, f"Provider should be None but got '{provider.name}'"


def test_repr_connected_to_local(networks_connected_to_tester):
    actual = repr(networks_connected_to_tester)
    expected = f"<NetworkManager active_provider=<Test chain_id={DEFAULT_TEST_CHAIN_ID}>>"
    assert actual == expected

    # Check individual network
    actual = repr(networks_connected_to_tester.provider.network)
    expected = f"<ethereum:local chain_id={DEFAULT_TEST_CHAIN_ID}>"
    assert actual == expected


def test_repr_disconnected(networks_disconnected):
    assert repr(networks_disconnected) == "<NetworkManager>"
    assert repr(networks_disconnected.ethereum) == "<ethereum>"
    assert repr(networks_disconnected.ethereum.local) == "<ethereum:local>"
    assert repr(networks_disconnected.ethereum.sepolia) == "<ethereum:sepolia chain_id=11155111>"


def test_get_provider_from_choice_custom_provider(networks_connected_to_tester):
    uri = "https://geth:1234567890abcdef@geth.foo.bar/"
    provider = networks_connected_to_tester.get_provider_from_choice(f"ethereum:local:{uri}")
    assert uri in provider.connection_id
    assert provider.name == "node"
    assert provider.uri == uri
    assert provider.network.name == "local"  # Network was specified to be local!
    assert provider.network.ecosystem.name == "ethereum"


def test_get_provider_from_choice_custom_adhoc_ecosystem(networks_connected_to_tester):
    uri = "https://geth:1234567890abcdef@geth.foo.bar/"
    provider = networks_connected_to_tester.get_provider_from_choice(uri)
    assert provider.name == "node"
    assert provider.uri == uri
    assert provider.network.name == "custom"
    assert provider.network.ecosystem.name == "ethereum"


def test_parse_network_choice_same_provider(chain, networks_connected_to_tester, get_context):
    context = get_context()
    start_count = len(context.connected_providers)
    original_block_number = chain.blocks.height
    object_id = id(chain.provider)

    with context:
        assert id(chain.provider) == object_id
        count = len(context.connected_providers)

        # Does not create a new provider since it is the same chain ID
        assert count == start_count

    assert id(chain.provider) == object_id
    assert len(context.connected_providers) == start_count
    assert chain.blocks.height == original_block_number

    for provider in context.connected_providers.values():
        assert provider._web3 is not None


@pytest.mark.xdist_group(name="multiple-eth-testers")
def test_parse_network_choice_new_chain_id(get_provider_with_unused_chain_id, get_context):
    start_count = len(get_context().connected_providers)
    context = get_provider_with_unused_chain_id()
    with context:
        count = len(context.connected_providers)

        assert context._provider.chain_id != DEFAULT_TEST_CHAIN_ID

        # Creates new provider since it has a new chain ID
        assert count == start_count + 1

    for provider in context.connected_providers.values():
        assert provider._web3 is not None


@pytest.mark.xdist_group(name="multiple-eth-testers")
def test_parse_network_choice_disconnect_after(get_provider_with_unused_chain_id):
    context = get_provider_with_unused_chain_id()
    with context as provider:
        connection_id = provider.connection_id
        assert connection_id in context.connected_providers

    assert connection_id not in context.connected_providers


@pytest.mark.xdist_group(name="multiple-eth-testers")
def test_parse_network_choice_multiple_contexts(
    eth_tester_provider, get_provider_with_unused_chain_id
):
    first_context = get_provider_with_unused_chain_id()
    assert (
        eth_tester_provider.chain_id == DEFAULT_TEST_CHAIN_ID
    ), "Test setup failed - expecting to start on default chain ID"
    assert eth_tester_provider.make_request("eth_chainId") == DEFAULT_TEST_CHAIN_ID

    with first_context:
        start_count = len(first_context.connected_providers)
        expected_next_count = start_count + 1
        second_context = get_provider_with_unused_chain_id()
        with second_context:
            # Second context should already know about connected providers
            assert len(first_context.connected_providers) == expected_next_count
            assert len(second_context.connected_providers) == expected_next_count

    assert eth_tester_provider.chain_id == DEFAULT_TEST_CHAIN_ID
    assert eth_tester_provider.make_request("eth_chainId") == DEFAULT_TEST_CHAIN_ID


def test_getattr_ecosystem_with_hyphenated_name(networks, ethereum):
    networks.ecosystems["hyphen-in-name"] = networks.ecosystems["ethereum"]
    assert networks.hyphen_in_name  # Make sure does not raise AttributeError
    del networks.ecosystems["hyphen-in-name"]


def test_getattr_custom_ecosystem(networks, custom_networks_config_dict, project):
    data = copy.deepcopy(custom_networks_config_dict)
    data["networks"]["custom"][0]["ecosystem"] = "custom-ecosystem"

    with project.temp_config(**data):
        actual = getattr(networks, "custom_ecosystem")
        assert isinstance(actual, EcosystemAPI)


@pytest.mark.parametrize("scheme", ("http", "https"))
def test_create_custom_provider_http(networks, scheme):
    provider = networks.create_custom_provider(f"{scheme}://example.com")
    assert provider.uri == f"{scheme}://example.com"


@pytest.mark.parametrize("scheme", ("ws", "wss"))
def test_create_custom_provider_ws(networks, scheme):
    with pytest.raises(NetworkError):
        networks.create_custom_provider(f"{scheme}://example.com")


def test_create_custom_provider_ipc(networks):
    provider = networks.create_custom_provider("path/to/geth.ipc")
    assert provider.ipc_path == Path("path/to/geth.ipc")

    # The IPC path should not be in URI field, different parts
    # of codebase may expect an actual URI.
    assert provider.uri != provider.ipc_path


def test_ecosystems(networks):
    actual = networks.ecosystems
    assert "ethereum" in actual
    assert actual["ethereum"].name == "ethereum"


def test_ecosystems_include_custom(networks, custom_networks_config_dict, project):
    data = copy.deepcopy(custom_networks_config_dict)
    data["networks"]["custom"][0]["ecosystem"] = "custom-ecosystem"
    with project.temp_config(**data):
        actual = networks.ecosystems

    assert "custom-ecosystem" in actual


def test_ecosystems_when_custom_has_bad_base_ecosystem(
    networks, custom_networks_config_dict, project
):
    data = copy.deepcopy(custom_networks_config_dict)
    eco_name = "custom-ecosystem-bad"
    eco_plugin_name = "plugin-ecosystem-not-installed"
    # Only hits error if ecosystem is custom because it is unknown.
    data["networks"]["custom"][0]["ecosystem"] = eco_name
    # The plugin base is for the class-implementation. If it is not a real plugin,
    # it should fail nicely.
    data["networks"]["custom"][0]["base_ecosystem_plugin"] = eco_plugin_name
    expected = (
        rf"Custom network '{eco_name}:apenet' specified unknown "
        rf"base-ecosystem class '{eco_plugin_name}'\. "
        rf"Are you missing plugin 'ape-{eco_plugin_name}'\?"
    )
    with project.temp_config(**data):
        with pytest.raises(NetworkError, match=expected):
            _ = networks.ecosystems


def test_fork_network_not_forkable(networks, eth_tester_provider):
    """
    Show correct failure when trying to fork the local network.
    """
    expected = "Unable to fork network 'local'."
    with pytest.raises(NetworkError, match=expected):
        with networks.fork():
            pass


def test_fork_no_providers(networks, mock_sepolia, disable_fork_providers):
    """
    Show correct failure when trying to fork without
    ape-hardhat or ape-foundry installed.
    """
    expected = "No providers for network 'sepolia-fork'."
    with pytest.raises(NetworkError, match=expected):
        with networks.fork():
            pass


def test_fork_use_non_existing_provider(networks, mock_sepolia):
    """
    Show correct failure when specifying a non-existing provider.
    """
    expected = "No provider named 'NOT_EXISTS' in network 'sepolia-fork' in ecosystem 'ethereum'.*"
    with pytest.raises(ProviderNotFoundError, match=expected):
        with networks.fork(provider_name="NOT_EXISTS"):
            pass


def test_fork(networks, mock_sepolia, mock_fork_provider):
    """
    Happy-path fork test.
    """
    ctx = networks.fork()
    assert ctx._disconnect_after is True
    with ctx as provider:
        assert provider.name == "mock"
        assert provider.network.name == "sepolia-fork"


def test_fork_specify_provider(networks, mock_sepolia, mock_fork_provider):
    """
    Happy-path fork test when specifying the provider.
    """
    ctx = networks.fork(provider_name="mock")
    assert ctx._disconnect_after is True
    with ctx as provider:
        assert provider.name == "mock"
        assert provider.network.name == "sepolia-fork"


def test_fork_with_provider_settings(networks, mock_sepolia, mock_fork_provider):
    """
    Show it uses the given provider settings.
    """
    settings = {"fork": {"ethereum": {"sepolia": {"block_number": 123}}}}
    with networks.fork(provider_settings=settings):
        actual = mock_fork_provider.partial_call
        assert actual[1]["provider_settings"] == settings


def test_fork_with_positive_block_number(networks, mock_sepolia, mock_fork_provider):
    block_id = 123
    with networks.fork(block_number=block_id):
        call = mock_fork_provider.partial_call

    settings = call[1]["provider_settings"]["fork"]["ethereum"]["sepolia"]
    actual = settings["block_number"]
    assert actual == block_id


def test_fork_with_negative_block_number(
    networks, mock_sepolia, mock_fork_provider, eth_tester_provider
):
    # Mine so we are past genesis.
    block_id = -1
    block = eth_tester_provider.get_block("latest")
    mock_fork_provider.get_block.return_value = block

    with networks.fork(block_number=block_id):
        call = mock_fork_provider.partial_call

    actual = call[1]["provider_settings"]["fork"]["ethereum"]["sepolia"]["block_number"]
    expected = block.number - 1  # Relative to genesis!
    assert actual == expected


def test_fork_past_genesis(networks, mock_sepolia, mock_fork_provider, eth_tester_provider):
    block_id = -10_000_000_000
    with pytest.raises(NetworkError, match="Unable to fork past genesis block."):
        with networks.fork(block_number=block_id):
            pass


def test_getitem(networks):
    ethereum = networks["ethereum"]
    assert ethereum.name == "ethereum"
    assert isinstance(ethereum, EcosystemAPI)


def test_network_names(networks, custom_networks_config_dict, project):
    data = copy.deepcopy(custom_networks_config_dict)
    with project.temp_config(**data):
        actual = networks.network_names
        assert LOCAL_NETWORK_NAME in actual
        assert "mainnet" in actual  # Normal
        assert "mainnet-fork" in actual  # Forked
        assert "apenet" in actual  # Custom
        assert "apenet-fork" in actual  # Custom forked


def test_custom_networks_defined_in_non_local_project(custom_networks_config_dict):
    """
    Showing we can read and use custom networks that are not defined
    in the local project.
    """
    # Ensure we are using a name that is not used anywhere else, for accurte testing.
    net_name = "customnetdefinedinnonlocalproj"
    eco_name = "customecosystemnotdefinedyet"
    custom_networks = copy.deepcopy(custom_networks_config_dict)
    custom_networks["networks"]["custom"][0]["name"] = net_name
    custom_networks["networks"]["custom"][0]["ecosystem"] = eco_name

    with ape.Project.create_temporary_project(config_override=custom_networks) as temp_project:
        nm = temp_project.network_manager
        ecosystem = nm.get_ecosystem(eco_name)
        assert ecosystem.name == eco_name
        network = ecosystem.get_network(net_name)
        assert network.name == net_name
