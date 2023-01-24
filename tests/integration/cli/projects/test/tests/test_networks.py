import shutil

from ape.exceptions import ProviderNotConnectedError


def test_networks_context_does_not_disconnect(networks):
    try:
        assert networks.provider.web3
    except ProviderNotConnectedError:
        # Show more info for debugging purposes
        context = networks.ethereum.local.use_provider("test")
        error_output = f"""
        ape: {shutil.which('ape')},
        connected_providers: {', '.join([pid for pid in context.connected_providers.keys()])},
        """
        assert False, f"Provider lost connection!\n{error_output}"

    context = networks.ethereum.local.use_provider("test")

    with context as provider:
        assert provider

    # Ensure we are still connected
    assert networks.provider.web3
