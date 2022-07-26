import pytest

from ape.exceptions import NetworkError


def test_get_network_choices_filter_ecosystem(networks):
    actual = {c for c in networks.get_network_choices(ecosystem_filter="ethereum")}
    expected = {c for c in networks.get_network_choices()}
    assert len(actual) == 27
    assert actual == expected


def test_get_network_choices_filter_network(networks):
    actual = {c for c in networks.get_network_choices(network_filter="mainnet-fork")}
    assert actual == set()


def test_get_network_choices_filter_provider(networks):
    actual = {c for c in networks.get_network_choices(provider_filter="test")}
    expected = {"::test", ":local", "ethereum:local", "ethereum:local:test", "ethereum"}
    assert actual == expected


def test_get_provider_when_no_default(networks):
    ethereum = networks.get_ecosystem("ethereum")
    network = ethereum.get_network("rinkeby-fork")
    with pytest.raises(NetworkError) as err:
        # Not provider installed out-of-the-box for rinkeby-fork network
        network.get_provider()

    assert "No default provider for network 'rinkeby-fork'" in str(err.value)


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
