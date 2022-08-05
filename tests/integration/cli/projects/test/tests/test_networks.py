def test_networks_context_does_not_disconnect(networks):
    assert networks.provider.web3

    context = networks.ethereum.local.use_provider("test")

    with context as provider:
        assert provider

    # Ensure we are still connected
    assert networks.provider.web3
