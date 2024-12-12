from ape_ethereum.proxies import ProxyType

"""
NOTE: Most proxy tests are in `geth/test_proxy.py`.
"""


def test_minimal_proxy(ethereum, minimal_proxy, chain):
    actual = ethereum.get_proxy_info(minimal_proxy.address)
    assert actual is not None
    assert actual.type == ProxyType.Minimal
    # It is the placeholder value still.
    assert actual.target == "0xBEbeBeBEbeBebeBeBEBEbebEBeBeBebeBeBebebe"
    # Show getting the contract using the proxy address.
    contract = chain.contracts.instance_at(minimal_proxy.address)
    assert contract.contract_type.abi == []  # No target ABIs; no proxy ABIs either.
