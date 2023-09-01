import pytest

from ape_ethereum.proxies import ProxyType
from ape_ethereum.proxies import minimal_proxy as minimal_proxy_container


@pytest.fixture
def minimal_proxy(owner):
    return owner.deploy(minimal_proxy_container)


def test_minimal_proxy(ethereum, minimal_proxy):
    actual = ethereum.get_proxy_info(minimal_proxy.address)
    assert actual is not None
    assert actual.type == ProxyType.Minimal
    # It is the placeholder value still.
    assert actual.target == "0xBEbeBeBEbeBebeBeBEBEbebEBeBeBebeBeBebebe"
