def test_can_use_built_in_fixtures(chain, capsys):
    assert True


def test_use_networks_fixture(networks):
    with networks.ethereum.local.use_provider("test") as provider:
        assert provider
