from eth_pydantic_types import HexBytes

from ape_ethereum.proxies import ProxyType
from tests.conftest import geth_process_test


@geth_process_test
def test_standard_proxy(project, owner, geth_contract, ethereum):
    target = geth_contract.address
    contract_instance = owner.deploy(project.ERC1967Proxy, target, HexBytes(""))
    actual = ethereum.get_proxy_info(contract_instance.address)
    assert actual is not None
    assert actual.type == ProxyType.Standard
    assert actual.target == target


@geth_process_test
def test_beacon_proxy(project, geth_contract, owner, ethereum):
    target = geth_contract.address
    beacon_instance = owner.deploy(project.beacon, target)
    beacon = beacon_instance.address

    contract_instance = owner.deploy(project.BeaconProxy, beacon, HexBytes(""))

    actual = ethereum.get_proxy_info(contract_instance.address)
    assert actual is not None
    assert actual.type == ProxyType.Beacon
    assert actual.target == target


@geth_process_test
def test_uups_proxy(project, geth_contract, owner, ethereum):
    target = geth_contract.address
    contract_instance = owner.deploy(project.Uups, HexBytes("0x2beb1711"), target)
    actual = ethereum.get_proxy_info(contract_instance.address)
    assert actual is not None
    assert actual.type == ProxyType.UUPS
    assert actual.target == target


@geth_process_test
def test_gnosis_safe(project, geth_contract, owner, ethereum, chain):
    # Setup a proxy contract.
    target = geth_contract.address
    proxy_instance = owner.deploy(project.SafeProxy, target)

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
def test_openzeppelin(project, geth_contract, owner, ethereum, sender):
    constructor_contract = owner.deploy(project.SolFallbackAndReceive)
    target = geth_contract.address
    contract_instance = owner.deploy(
        project.UpgradeabilityProxy, constructor_contract.address, target
    )
    actual = ethereum.get_proxy_info(contract_instance.address)
    assert actual is not None
    assert actual.type == ProxyType.OpenZeppelin
    assert actual.target == target


@geth_process_test
def test_delegate(project, geth_contract, owner, ethereum):
    target = geth_contract.address
    contract_instance = owner.deploy(project.ERCProxy, target)
    actual = ethereum.get_proxy_info(contract_instance.address)
    assert actual is not None
    assert actual.type == ProxyType.Delegate
    assert actual.target == target


@geth_process_test
def test_aragon_app_upgradeable(project, geth_contract, owner, ethereum):
    from eth_utils import keccak

    target = geth_contract.address
    kernel = owner.deploy(project.AragonKernelMock)
    app_id = keccak(text="ape.test.aragon.app")
    namespace = keccak(text="base")
    kernel.setApp(namespace, app_id, target, sender=owner)

    contract_instance = owner.deploy(project.AragonAppProxyUpgradeable, kernel.address, app_id)
    actual = ethereum.get_proxy_info(contract_instance.address)
    assert actual is not None
    assert actual.type == ProxyType.AragonAppUpgradeable
    assert actual.target == target
