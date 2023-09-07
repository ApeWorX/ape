from ape_ethereum.proxies import ProxyType

"""
NOTE: Most proxy tests are in `geth/test_proxy.py`.
"""


def test_minimal_proxy(ethereum, minimal_proxy):
    actual = ethereum.get_proxy_info(minimal_proxy.address)
    assert actual is not None
    assert actual.type == ProxyType.Minimal
    # It is the placeholder value still.
    assert actual.target == "0xBEbeBeBEbeBebeBeBEBEbebEBeBeBebeBeBebebe"
