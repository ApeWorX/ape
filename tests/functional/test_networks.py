import pytest

from ape.exceptions import NetworkError


@pytest.fixture
def network_with_no_providers(ethereum):
    network = ethereum.get_network("rinkeby-fork")
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
        ":kovan",
        ":kovan:geth",
        ":local",
        ":mainnet",
        ":mainnet:geth",
        ":rinkeby",
        ":rinkeby:geth",
        ":ropsten",
        ":ropsten:geth",
        "ethereum",
        "ethereum:goerli",
        "ethereum:goerli:geth",
        "ethereum:kovan",
        "ethereum:kovan:geth",
        "ethereum:local",
        "ethereum:local:geth",
        "ethereum:local:test",
        "ethereum:mainnet",
        "ethereum:mainnet:geth",
        "ethereum:rinkeby",
        "ethereum:rinkeby:geth",
        "ethereum:ropsten",
        "ethereum:ropsten:geth",
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
    assert actual == expected


def test_get_provider_when_no_default(network_with_no_providers):
    with pytest.raises(NetworkError) as err:
        # Not provider installed out-of-the-box for rinkeby-fork network
        provider = network_with_no_providers.get_provider()
        assert not provider, f"Provider should be None but got '{provider.name}'"

    assert f"No default provider for network '{network_with_no_providers.name}'" in str(err.value)


def test_get_provider_when_not_found(networks):
    ethereum = networks.get_ecosystem("ethereum")
    network = ethereum.get_network("rinkeby-fork")
    with pytest.raises(NetworkError) as err:
        network.get_provider("test")

    assert "'test' is not a valid provider for network 'rinkeby-fork'" in str(err.value)


def test_repr(networks_connected_to_tester):
    assert (
        repr(networks_connected_to_tester) == "<NetworkManager active_provider=<test chain_id=61>>"
    )

    # Check individual network
    assert repr(networks_connected_to_tester.provider.network) == "<local chain_id=61>"


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
