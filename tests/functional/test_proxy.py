from typing import TYPE_CHECKING, Optional

from eth_pydantic_types import HexBytes

from ape.contracts.base import ContractContainer
from ape_ethereum.proxies import ProxyType
from ape_test.provider import LocalProvider

if TYPE_CHECKING:
    from ape.types import AddressType, BlockID

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


def test_provider_not_supports_get_storage(
    get_contract_type, owner, vyper_contract_instance, ethereum, chain, networks
):
    """
    The get storage slot RPC is required to detect this proxy, so it won't work
    on EthTester provider. However, we can make sure that it doesn't try to
    call `get_storage()` more than once.
    """

    class MyProvider(LocalProvider):
        times_get_storage_was_called: int = 0

        def get_storage(  # type: ignore[empty-body]
            self, address: "AddressType", slot: int, block_id: Optional["BlockID"] = None
        ) -> "HexBytes":
            self.times_get_storage_was_called += 1
            raise NotImplementedError()

    my_provider = MyProvider(name="test", network=ethereum.local)
    my_provider._web3 = chain.provider._web3

    _type = get_contract_type("beacon")
    beacon_contract = ContractContainer(_type)
    target = vyper_contract_instance.address
    beacon_instance = owner.deploy(beacon_contract, target)
    beacon = beacon_instance.address

    _type = get_contract_type("BeaconProxy")
    contract = ContractContainer(_type)
    contract_instance = owner.deploy(contract, beacon, HexBytes(""))

    # Ensure not already cached.
    if contract_instance.address in chain.contracts.proxy_infos:
        del chain.contracts.proxy_infos[contract_instance.address]

    init_provider = networks.active_provider
    networks.active_provider = my_provider
    try:
        actual = ethereum.get_proxy_info(contract_instance.address)
    finally:
        networks.active_provider = init_provider

    assert actual is None  # Because of provider.
    assert my_provider.times_get_storage_was_called == 1
