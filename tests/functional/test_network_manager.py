import pytest

from ape.exceptions import NetworkError
from ape.utils import DEFAULT_TEST_CHAIN_ID


class NewChainID:
    chain_id = 12345678987654

    def __call__(self, *args, **kwargs) -> int:
        self.chain_id += 1
        return self.chain_id


chain_id_factory = NewChainID()

DEFAULT_CHOICES = {
    "::geth",
    "::test",
    ":goerli",
    ":goerli:geth",
    ":sepolia",
    ":sepolia:geth",
    ":local",
    ":mainnet",
    ":mainnet:geth",
    "ethereum",
    "ethereum::test",
    "ethereum::geth",
    "ethereum:goerli",
    "ethereum:goerli:geth",
    "ethereum:sepolia",
    "ethereum:sepolia:geth",
    "ethereum:local",
    "ethereum:local:geth",
    "ethereum:local:test",
    "ethereum:mainnet",
    "ethereum:mainnet:geth",
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
    network = ethereum.get_network("goerli-fork")
    default_provider = network.default_provider
    providers = network.__dict__["providers"]

    if default_provider or providers:
        # Handle user running tests with forked-network plugins installed
        network._default_provider = None
        network.__dict__["providers"] = []

    yield network

    if default_provider or providers:
        network._default_provider = default_provider
        network.__dict__["providers"] = providers


def test_get_network_choices(networks, ethereum, mocker):
    # Simulate having a provider like foundry installed.
    mock_provider = mocker.MagicMock()
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
        ":mainnet:geth",
        "ethereum",
        "ethereum:mainnet",
        "ethereum:mainnet:geth",
    }
    assert mainnet_choices.issubset(actual)


def test_get_network_choices_filter_provider(networks):
    actual = {c for c in networks.get_network_choices(provider_filter="test")}
    expected = {"::test", ":local", "ethereum:local", "ethereum:local:test", "ethereum"}
    assert all(e in actual for e in expected)


def test_get_provider_when_no_default(network_with_no_providers):
    expected = f"No default provider for network '{network_with_no_providers.name}'"
    with pytest.raises(NetworkError, match=expected):
        # Not provider installed out-of-the-box for goerli-fork network
        provider = network_with_no_providers.get_provider()
        assert not provider, f"Provider should be None but got '{provider.name}'"


def test_repr_connected_to_local(networks_connected_to_tester):
    actual = repr(networks_connected_to_tester)
    expected = f"<NetworkManager active_provider=<test chain_id={DEFAULT_TEST_CHAIN_ID}>>"
    assert actual == expected

    # Check individual network
    actual = repr(networks_connected_to_tester.provider.network)
    expected = f"<ethereum:local chain_id={DEFAULT_TEST_CHAIN_ID}>"
    assert actual == expected


def test_repr_disconnected(networks_disconnected):
    assert repr(networks_disconnected) == "<NetworkManager>"
    assert repr(networks_disconnected.ethereum) == "<ethereum>"
    assert repr(networks_disconnected.ethereum.local) == "<ethereum:local>"
    assert repr(networks_disconnected.ethereum.goerli) == "<ethereum:goerli chain_id=5>"


def test_get_provider_from_choice_adhoc_provider(networks_connected_to_tester):
    uri = "https://geth:1234567890abcdef@geth.foo.bar/"
    provider = networks_connected_to_tester.get_provider_from_choice(f"ethereum:local:{uri}")
    assert provider.name == "geth"
    assert provider.uri == uri
    assert provider.network.name == "local"
    assert provider.network.ecosystem.name == "ethereum"


def test_get_provider_from_choice_adhoc_ecosystem(networks_connected_to_tester):
    uri = "https://geth:1234567890abcdef@geth.foo.bar/"
    provider = networks_connected_to_tester.get_provider_from_choice(uri)
    assert provider.name == "geth"
    assert provider.uri == uri
    assert provider.network.name == "adhoc"
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
def test_disconnect_after(get_provider_with_unused_chain_id):
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
    assert eth_tester_provider._make_request("eth_chainId") == DEFAULT_TEST_CHAIN_ID

    with first_context:
        start_count = len(first_context.connected_providers)
        expected_next_count = start_count + 1
        second_context = get_provider_with_unused_chain_id()
        with second_context:
            # Second context should already know about connected providers
            assert len(first_context.connected_providers) == expected_next_count
            assert len(second_context.connected_providers) == expected_next_count

    assert eth_tester_provider.chain_id == DEFAULT_TEST_CHAIN_ID
    assert eth_tester_provider._make_request("eth_chainId") == DEFAULT_TEST_CHAIN_ID


def test_getattr_ecosystem_with_hyphenated_name(networks, ethereum):
    networks.ecosystems["hyphen-in-name"] = networks.ecosystems["ethereum"]
    assert networks.hyphen_in_name  # Make sure does not raise AttributeError
    del networks.ecosystems["hyphen-in-name"]
