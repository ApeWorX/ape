import pytest

from ape.exceptions import ProviderNotConnectedError
from ape.utils.basemodel import ManagerAccessMixin


class CustomClass(ManagerAccessMixin):
    pass


@pytest.mark.parametrize("accessor", (CustomClass, CustomClass()))
def test_provider(accessor, eth_tester_provider):
    assert accessor.provider == eth_tester_provider


@pytest.mark.parametrize("accessor", (CustomClass, CustomClass()))
def test_provider_not_active(networks, accessor):
    initial = networks.active_provider
    networks.active_provider = None
    try:
        with pytest.raises(ProviderNotConnectedError):
            _ = accessor.provider
    finally:
        networks.active_provider = initial
