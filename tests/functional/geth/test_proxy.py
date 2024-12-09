from eth_pydantic_types import HexBytes
from eth_utils import to_checksum_address

from ape.contracts import ContractContainer
from ape_ethereum.proxies import ProxyType
from tests.conftest import geth_process_test


@geth_process_test
def test_standard_proxy(get_contract_type, owner, geth_contract, ethereum):
    """
    NOTE: Geth is used here because EthTester does not implement getting storage slots.
    """
    _type = get_contract_type("eip1967")
    contract = ContractContainer(_type)
    target = geth_contract.address
    contract_instance = owner.deploy(contract, target, HexBytes(""))
    actual = ethereum.get_proxy_info(contract_instance.address)
    assert actual is not None
    assert actual.type == ProxyType.Standard
    assert actual.target == target


@geth_process_test
def test_beacon_proxy(get_contract_type, geth_contract, owner, ethereum):
    """
    NOTE: Geth is used here because EthTester does not implement getting storage slots.
    """
    _type = get_contract_type("beacon")
    beacon_contract = ContractContainer(_type)
    target = geth_contract.address
    beacon_instance = owner.deploy(beacon_contract, target)
    beacon = beacon_instance.address

    _type = get_contract_type("BeaconProxy")
    contract = ContractContainer(_type)
    contract_instance = owner.deploy(contract, beacon, HexBytes(""))

    actual = ethereum.get_proxy_info(contract_instance.address)
    assert actual is not None
    assert actual.type == ProxyType.Beacon
    assert actual.target == target


@geth_process_test
def test_uups_proxy(get_contract_type, geth_contract, owner, ethereum):

    _type = get_contract_type("Uups")
    contract = ContractContainer(_type)

    target = geth_contract.address

    contract_instance = owner.deploy(contract, HexBytes("0x2beb1711"), target)

    actual = ethereum.get_proxy_info(contract_instance.address)
    assert actual is not None
    assert actual.type == ProxyType.UUPS
    assert actual.target == target


@geth_process_test
def test_minimal_proxy(get_contract_type, geth_contract, owner, ethereum):

    _type = get_contract_type("MinimalProxyFactory")
    contract = ContractContainer(_type)                         

    target = geth_contract.address
    # deploy MinimalProxyFactory.vy
    factory = owner.deploy(contract)
    vyper_proxy = factory.deploy(target, sender=owner)
    proxy_address = to_checksum_address("0x" + (vyper_proxy.logs[0]["data"].hex())[-40:])
    actual = ethereum.get_proxy_info(proxy_address)

    assert actual is not None
    assert actual.type == ProxyType.Minimal
    assert actual.target == target


@geth_process_test
def test_gnosis_safe(get_contract_type, geth_contract, owner, ethereum):

    _type = get_contract_type("GnosisSafe")
    contract = ContractContainer(_type)

    target = geth_contract.address

    contract_instance = owner.deploy(contract, target)

    actual = ethereum.get_proxy_info(contract_instance.address)

    assert actual is not None
    assert actual.type == ProxyType.GnosisSafe
    assert actual.target == target
