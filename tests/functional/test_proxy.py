from typing import TYPE_CHECKING, Optional

import pytest
from eth_pydantic_types import HexBytes

from ape_ethereum.proxies import ProxyType
from ape_test.provider import LocalProvider

if TYPE_CHECKING:
    from ape.types import AddressType, BlockID

"""
NOTE: Most proxy tests are in `geth/test_proxy.py`.
"""


@pytest.fixture
def target(project, owner):
    vyper_contract = owner.deploy(project.VyperContract, 0)
    return vyper_contract.address


def test_minimal_proxy(ethereum, minimal_proxy, chain):
    placeholder = "0xBEbeBeBEbeBebeBeBEBEbebEBeBeBebeBeBebebe"
    if placeholder in chain.contracts:
        del chain.contracts[placeholder]

    chain.provider.network.__dict__["explorer"] = None  # Ensure no explorer, messes up test.
    assert minimal_proxy.contract_type.abi == []  # No target ABIs; no proxy ABIs either.


def test_clones(project, owner, ethereum, target):
    factory = owner.deploy(project.ClonesFactory)
    tx = factory.deployClonesProxy(target, sender=owner)
    proxy_address = tx.events[0].addr
    actual = ethereum.get_proxy_info(proxy_address)
    assert actual is not None
    assert actual.type == ProxyType.Clones
    assert actual.target == target


def test_CWIA(project, owner, ethereum, target):
    factory = owner.deploy(project.ExampleCloneFactory, target)
    tx = factory.createClone(0, 0, 0, 0, sender=owner)
    proxy_address = tx.events[0].addr
    actual = ethereum.get_proxy_info(proxy_address)
    assert actual is not None
    assert actual.type == ProxyType.CWIA
    assert actual.target == target


def test_Solady(project, owner, ethereum, target):
    factory = owner.deploy(project.SoladyFactory)

    # test Solady Push proxy
    tx = factory.deploySoladyPush(target, sender=owner)
    proxy_address = tx.events[0].addr
    actual = ethereum.get_proxy_info(proxy_address)
    assert actual is not None
    assert actual.type == ProxyType.SoladyPush0
    assert actual.target == target

    # test Solady CWIA proxy
    tx = factory.deploySoladyCWIA(target, sender=owner)
    proxy_address = tx.events[0].addr
    actual = ethereum.get_proxy_info(proxy_address)
    assert actual is not None

    # Solady proxies are basically ProxyType.Minimal (just an efficient route of doing so).
    assert actual.type == ProxyType.Minimal

    assert actual.target == target


def test_OldCWIA(project, owner, ethereum, target):
    contract_instance = owner.deploy(project.Template)
    tx = contract_instance.clone2(target, 0, sender=owner)
    proxy_address = tx.events[0].addr
    actual = ethereum.get_proxy_info(proxy_address)
    assert actual is not None
    assert actual.type == ProxyType.OldCWIA
    assert actual.target == target


def test_Vyper(project, owner, ethereum, target):
    factory = owner.deploy(project.VyperFactory)
    tx = factory.create_proxy(target, sender=owner)
    proxy_address = tx.events[0].target
    actual = ethereum.get_proxy_info(proxy_address)
    assert actual is not None

    # Vyper forwarder sproxies are basically ProxyType.Minimal (just an efficient route of doing so).
    assert actual.type == ProxyType.Minimal

    assert actual.target == target


def test_SudoswapCWIA(project, owner, ethereum, target):
    contract_instance = owner.deploy(project.SudoswapCWIAFactory)
    tx = contract_instance.deploycloneERC721ETHPair(target, 0, 0, 0, 0, 0, sender=owner)
    proxy_address = tx.events[0].addr
    actual = ethereum.get_proxy_info(proxy_address)
    assert actual is not None
    assert actual.type == ProxyType.SudoswapCWIA
    assert actual.target == target


def test_provider_not_supports_get_storage(
    project, owner, vyper_contract_instance, ethereum, chain, networks
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

    target = vyper_contract_instance.address
    beacon_instance = owner.deploy(project.beacon, target)
    beacon = beacon_instance.address

    contract_instance = owner.deploy(project.BeaconProxy, beacon, HexBytes(""))

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
