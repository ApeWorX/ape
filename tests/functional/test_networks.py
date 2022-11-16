import pytest

from ape.exceptions import NetworkError
from ape_test.provider import CHAIN_ID


class NewChainID:
    chain_id = 12345678987654

    def __call__(self, *args, **kwargs) -> int:
        self.chain_id += 1
        return self.chain_id


chain_id_factory = NewChainID()


@pytest.fixture
def get_provider_with_unused_chain_id(networks_connected_to_tester):
    networks = networks_connected_to_tester

    def fn():
        new_provider = networks.provider.copy()
        new_provider.cached_chain_id = chain_id_factory()
        context = networks.parse_network_choice("ethereum:local:test")
        context._provider = new_provider
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


def test_get_network_choices_filter_ecosystem(networks):
    actual = {c for c in networks.get_network_choices(ecosystem_filter="ethereum")}
    all_choices = {
        "::geth",
        "::test",
        ":goerli",
        ":goerli:geth",
        ":local",
        ":mainnet",
        ":mainnet:geth",
        "ethereum",
        "ethereum:goerli",
        "ethereum:goerli:geth",
        "ethereum:local",
        "ethereum:local:geth",
        "ethereum:local:test",
        "ethereum:mainnet",
        "ethereum:mainnet:geth",
    }
    assert all_choices.issubset(actual)


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
    with pytest.raises(NetworkError) as err:
        # Not provider installed out-of-the-box for goerli-fork network
        provider = network_with_no_providers.get_provider()
        assert not provider, f"Provider should be None but got '{provider.name}'"

    assert f"No default provider for network '{network_with_no_providers.name}'" in str(err.value)


def test_get_provider_when_not_found(networks):
    ethereum = networks.get_ecosystem("ethereum")
    network = ethereum.get_network("goerli-fork")
    with pytest.raises(NetworkError) as err:
        network.get_provider("test")

    assert "'test' is not a valid provider for network 'goerli-fork'" in str(err.value)


def test_repr_connected_to_local(networks_connected_to_tester):
    actual = repr(networks_connected_to_tester)
    expected = f"<NetworkManager active_provider=<test chain_id={CHAIN_ID}>>"
    assert actual == expected

    # Check individual network
    actual = repr(networks_connected_to_tester.provider.network)
    expected = f"<ethereum:local chain_id={CHAIN_ID}>"
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
    provider_id = id(chain.provider)

    with context:
        assert id(chain.provider) == provider_id
        count = len(context.connected_providers)

        # Does not create a new provider since it is the same chain ID
        assert count == start_count

    assert id(chain.provider) == provider_id
    assert len(context.connected_providers) == start_count
    assert chain.blocks.height == original_block_number

    for provider in context.connected_providers.values():
        assert provider._web3 is not None


def test_parse_network_choice_new_chain_id(get_provider_with_unused_chain_id, get_context):
    start_count = len(get_context().connected_providers)
    context = get_provider_with_unused_chain_id()
    with context:
        count = len(context.connected_providers)

        # Creates new provider since it has a new chain ID
        assert count == start_count + 1

    for provider in context.connected_providers.values():
        assert provider._web3 is not None


def test_parse_network_choice_multiple_contexts(get_provider_with_unused_chain_id):
    first_context = get_provider_with_unused_chain_id()
    with first_context:
        start_count = len(first_context.connected_providers)
        expected_next_count = start_count + 1
        second_context = get_provider_with_unused_chain_id()
        with second_context:
            # Second context should already know about connected providers
            assert len(first_context.connected_providers) == expected_next_count
            assert len(second_context.connected_providers) == expected_next_count


def test_block_times(ethereum):
    assert ethereum.goerli.block_time == 15


def test_ecosystems_when_default_network_not_exists(temp_config, caplog, networks):
    bad_network = "NOT_EXISTS"
    config = {"ethereum": {"default_network": bad_network}}
    with temp_config(config):
        assert networks.ecosystems

    err = caplog.records[-1].message
    assert err == (
        f"Failed setting default network: "
        f"'{bad_network}' is not a valid network for ecosystem 'ethereum'."
    )


def test_ecosystems_when_default_provider_not_exists(temp_config, caplog, networks):
    bad_provider = "NOT_EXISTS"
    config = {"ethereum": {"goerli": {"default_provider": bad_provider}}}
    with temp_config(config):
        assert networks.ecosystems

    err = caplog.records[-1].message
    assert err == (
        f"Failed setting default provider: "
        f"Provider '{bad_provider}' not found in network 'goerli'."
    )


def test_gas_limits(networks, config, project_with_source_files_contract):
    """
    Test the default gas limit configurations for local and live networks.
    """
    _ = project_with_source_files_contract  # Ensure use of project with default config
    assert networks.ethereum.goerli.gas_limit == "auto"
    assert networks.ethereum.local.gas_limit == "max"
