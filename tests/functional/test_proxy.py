from ape_ethereum.proxies import ProxyType

"""
NOTE: Most proxy tests are in `geth/test_proxy.py`.
"""


def test_minimal_proxy(ethereum, minimal_proxy_container, chain, owner):
    placeholder = "0xBEbeBeBEbeBebeBeBEBEbebEBeBeBebeBeBebebe"
    if placeholder in chain.contracts:
        del chain.contracts[placeholder]

    minimal_proxy = owner.deploy(minimal_proxy_container, sender=owner)
    chain.provider.network.__dict__["explorer"] = None  # Ensure no explorer, messes up test.
    actual = ethereum.get_proxy_info(minimal_proxy.address)
    assert actual is not None
    assert actual.type == ProxyType.Minimal
    # It is the placeholder value still.
    assert actual.target == placeholder

    # Show getting the contract using the proxy address.
    contract = chain.contracts.instance_at(minimal_proxy.address)
    abi = contract.contract_type.abi
    if isinstance(abi, list):
        assert abi == []
    # else: is messed up from other test (xdist).
