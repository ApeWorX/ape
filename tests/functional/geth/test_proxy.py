from eth_pydantic_types import HexBytes

from ape.contracts import ContractContainer
from ape_ethereum.proxies import ProxyType
from tests.conftest import geth_process_test


@geth_process_test
def test_standard_proxy(get_contract_type, owner, geth_contract, ethereum):
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
def test_gnosis_safe(safe_proxy_container, geth_contract, owner, ethereum, chain):
    # Setup a proxy contract.
    target = geth_contract.address
    proxy_instance = owner.deploy(safe_proxy_container, target)

    # (test)
    actual = ethereum.get_proxy_info(proxy_instance.address)
    assert actual is not None
    assert actual.type == ProxyType.GnosisSafe
    assert actual.target == target

    # Ensure we can call the proxy-method.
    assert proxy_instance.masterCopy()

    # Ensure we can call target methods.
    assert isinstance(proxy_instance.myNumber(), int)

    # Ensure this works with new instances.
    proxy_instance_ref_2 = chain.contracts.instance_at(proxy_instance.address)
    assert proxy_instance_ref_2.masterCopy()
    assert isinstance(proxy_instance_ref_2.myNumber(), int)


@geth_process_test
def test_openzeppelin(get_contract_type, geth_contract, owner, ethereum, sender):
    _type = get_contract_type("UpgradeabilityProxy")
    contract = ContractContainer(_type)

    target = geth_contract.address
    _type = get_contract_type("SolFallbackAndReceive")
    constructor_container = ContractContainer(_type)
    constructor_contract = owner.deploy(constructor_container)

    contract_instance = owner.deploy(contract, constructor_contract.address, target)

    actual = ethereum.get_proxy_info(contract_instance.address)
    assert actual is not None
    assert actual.type == ProxyType.OpenZeppelin
    assert actual.target == target


@geth_process_test
def test_delegate(get_contract_type, geth_contract, owner, ethereum):
    _type = get_contract_type("ERCProxy")
    contract = ContractContainer(_type)

    target = geth_contract.address

    contract_instance = owner.deploy(contract, target)

    actual = ethereum.get_proxy_info(contract_instance.address)

    assert actual is not None
    assert actual.type == ProxyType.Delegate
    assert actual.target == target
