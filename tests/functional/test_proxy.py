import pytest
from eth_utils import to_checksum_address

from ape.contracts import ContractContainer
from ape_ethereum.proxies import ProxyType

"""
NOTE: Most proxy tests are in `geth/test_proxy.py`.
"""


@pytest.fixture
def target(vyper_contract_container, owner):
    vyper_contract = owner.deploy(vyper_contract_container, 0)
    return vyper_contract.address


def test_minimal_proxy(ethereum, minimal_proxy, chain):
    actual = ethereum.get_proxy_info(minimal_proxy.address)
    assert actual is not None
    assert actual.type == ProxyType.Minimal
    # It is the placeholder value still.
    assert actual.target == "0xBEbeBeBEbeBebeBeBEBEbebEBeBeBebeBeBebebe"
    # Show getting the contract using the proxy address.
    contract = chain.contracts.instance_at(minimal_proxy.address)
    assert contract.contract_type.abi == []  # No target ABIs; no proxy ABIs either.


def test_clones(get_contract_type, owner, ethereum, target):
    _type = get_contract_type("ClonesFactory")
    contract = ContractContainer(_type)
    factory = owner.deploy(contract)
    clones_proxy = factory.deployClonesProxy(target, sender=owner)
    proxy_address = to_checksum_address("0x" + (clones_proxy.logs[0]["data"].hex())[-40:])
    actual = ethereum.get_proxy_info(proxy_address)
    assert actual is not None
    assert actual.type == ProxyType.Clones
    assert actual.target == target


def test_CWIA(get_contract_type, owner, ethereum, target):
    _type = get_contract_type("CWIA")
    contract = ContractContainer(_type)
    factory = owner.deploy(contract, target)
    clones_proxy = factory.createClone(0, 0, 0, 0, sender=owner)
    proxy_address = to_checksum_address("0x" + (clones_proxy.logs[0]["data"].hex())[-40:])
    actual = ethereum.get_proxy_info(proxy_address)
    assert actual is not None
    assert actual.type == ProxyType.CWIA
    assert actual.target == target


def test_Solady(get_contract_type, owner, ethereum, target):
    _type = get_contract_type("SoladyFactory")
    contract = ContractContainer(_type)
    factory = owner.deploy(contract)

    # test Solady Push proxy
    clones_proxy = factory.deploySoladyPush(target, sender=owner)
    proxy_address = to_checksum_address("0x" + (clones_proxy.logs[0]["data"].hex())[-40:])
    actual = ethereum.get_proxy_info(proxy_address)
    assert actual is not None
    assert actual.type == ProxyType.SoladyPush0
    assert actual.target == target

    # test Solady CWIA proxy
    clones_proxy = factory.deploySoladyCWIA(target, sender=owner)
    proxy_address = to_checksum_address("0x" + (clones_proxy.logs[0]["data"].hex())[-40:])
    actual = ethereum.get_proxy_info(proxy_address)
    assert actual is not None
    assert actual.type == ProxyType.SoladyCWIA
    assert actual.target == target


def test_SplitsCWIA(get_contract_type, owner, ethereum, target):
    _type = get_contract_type("SplitsCWIA")
    contract = ContractContainer(_type)
    factory = owner.deploy(contract, target)
    clones_proxy = factory.createClone(0, 0, 0, 0, sender=owner)
    proxy_address = to_checksum_address("0x" + (clones_proxy.logs[0]["data"].hex())[-40:])
    actual = ethereum.get_proxy_info(proxy_address)
    assert actual is not None
    assert actual.type == ProxyType.SplitsCWIA
    assert actual.target == target


def test_OldCWIA(get_contract_type, owner, ethereum, target):
    _type = get_contract_type("OldCWIA")
    contract = ContractContainer(_type)
    contract_instance = owner.deploy(contract)
    clones_proxy = contract_instance.clone1(0, sender=owner)
    proxy_address = to_checksum_address("0x" + (clones_proxy.logs[0]["data"].hex())[-40:])
    actual = ethereum.get_proxy_info(proxy_address)
    assert actual is not None
    assert actual.type == ProxyType.Standard
    assert actual.target == target


def test_Vyper(get_contract_type, owner, ethereum, target):
    _type = get_contract_type("VyperFactory")
    contract = ContractContainer(_type)
    factory = owner.deploy(contract)
    clones_proxy = factory.create_proxy(target, sender=owner)
    proxy_address = to_checksum_address("0x" + (clones_proxy.logs[0]["data"].hex())[-40:])
    actual = ethereum.get_proxy_info(proxy_address)
    assert actual is not None
    assert actual.type == ProxyType.Vyper
    assert actual.target == target


def test_SudoswapCWIA(get_contract_type, owner, ethereum, target):
    _type = get_contract_type("SudoswapCWIA")
    contract = ContractContainer(_type)
    contract_instance = owner.deploy(contract)
    clones_proxy = contract_instance.deploycloneERC721ETHPair(target, 0, 0, 0, 0, 0, sender=owner)
    proxy_address = to_checksum_address("0x" + (clones_proxy.logs[0]["data"].hex())[-40:])
    actual = ethereum.get_proxy_info(proxy_address)
    assert actual is not None
    assert actual.type == ProxyType.SudoswapCWIA
    assert actual.target == target

    clones_proxy = contract_instance.deploycloneERC1155ETHPair(target, 0, 0, 0, 0, 0, sender=owner)
    proxy_address = to_checksum_address("0x" + (clones_proxy.logs[0]["data"].hex())[-40:])
    actual = ethereum.get_proxy_info(proxy_address)
    assert actual is not None
    assert actual.type == ProxyType.SudoswapCWIA
    assert actual.target == target
