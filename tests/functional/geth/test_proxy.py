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
def test_gnosis_safe(project, geth_contract, owner, ethereum, chain, mocker):
    # Setup a proxy contract.
    target = geth_contract.address
    proxy_instance = owner.deploy(project.SafeProxy, target)

    # (test)
    storage_spy = mocker.spy(chain.provider.web3.eth, "get_storage_at")
    actual = ethereum.get_proxy_info(proxy_instance.address)
    assert actual is not None
    assert actual.type == ProxyType.GnosisSafe
    assert actual.target == target
    assert storage_spy.call_count == 1

    # Ensure we can call the proxy-method.
    assert proxy_instance.masterCopy()

    # Ensure we can call target methods.
    assert isinstance(proxy_instance.myNumber(), int)

    # Ensure this works with new instances.
    proxy_instance_ref_2 = chain.contracts.instance_at(proxy_instance.address)
    assert proxy_instance_ref_2.masterCopy()
    assert isinstance(proxy_instance_ref_2.myNumber(), int)


@geth_process_test
def test_non_proxy_without_delegatecall_skips_storage(geth_contract, ethereum, chain, mocker):
    storage_spy = mocker.spy(chain.provider.web3.eth, "get_storage_at")

    actual = ethereum.get_proxy_info(geth_contract.address)

    assert actual is None
    assert storage_spy.call_count == 0


@geth_process_test
def test_gnosis_safe_v150(project, geth_contract, owner, ethereum):
    target = geth_contract.address
    proxy_instance = owner.deploy(project.SafeProxyV150, target)

    actual = ethereum.get_proxy_info(proxy_instance.address)
    assert actual is not None
    assert actual.type == ProxyType.GnosisSafe
    assert actual.target == target


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


def _deploy_runtime(owner, deployer, runtime: bytes):
    n = len(runtime)
    init = (
        bytes([0x61])
        + n.to_bytes(2, "big")
        + bytes([0x80, 0x60, 15, 0x60, 0, 0x39, 0x61])
        + n.to_bytes(2, "big")
        + bytes([0x60, 0, 0xF3])
    )
    tx = deployer.deploy(init + runtime, sender=owner)
    return tx.return_value


@geth_process_test
def test_clones(project, geth_contract, owner, ethereum):
    target = geth_contract.address
    factory = owner.deploy(project.ClonesFactory)
    tx = factory.deployClonesProxy(target, sender=owner)
    actual = ethereum.get_proxy_info(tx.return_value)
    assert actual is not None
    assert actual.type == ProxyType.Clones
    assert actual.target == target


@geth_process_test
def test_cwia(project, geth_contract, owner, ethereum):
    target = geth_contract.address
    factory = owner.deploy(project.ExampleCloneFactory, target)
    tx = factory.createClone(0, 0, 0, 0, sender=owner)
    actual = ethereum.get_proxy_info(tx.return_value)
    assert actual is not None
    assert actual.type == ProxyType.CWIA
    assert actual.target == target


@geth_process_test
def test_solady_push0(project, geth_contract, owner, ethereum):
    target = geth_contract.address
    factory = owner.deploy(project.SoladyFactory)
    tx = factory.deploySoladyPush(target, sender=owner)
    actual = ethereum.get_proxy_info(tx.return_value)
    assert actual is not None
    assert actual.type == ProxyType.SoladyPush0
    assert actual.target == target


@geth_process_test
def test_solady_cwia_factory(project, geth_contract, owner, ethereum):
    target = geth_contract.address
    factory = owner.deploy(project.SoladyFactory)
    tx = factory.deploySoladyCWIA(target, sender=owner)
    actual = ethereum.get_proxy_info(tx.return_value)
    assert actual is not None
    assert actual.type == ProxyType.Minimal
    assert actual.target == target


@geth_process_test
def test_solady_cwia(project, geth_contract, owner, ethereum):
    target = geth_contract.address
    addr = target[2:]
    runtime = (
        "36602c57343d527f9e4ac34f21c619cefc926c8bd93b54bf5a39c7ab2127a895af1cc0691d7e3dff"
        "593da1005b363d3d373d3d3d3d610000806062363936013d73"
        f"{addr}"
        "5af43d3d93803e606057fd5bf3"
    )
    deployer = owner.deploy(project.RawDeployer)
    proxy = _deploy_runtime(owner, deployer, bytes.fromhex(runtime))
    actual = ethereum.get_proxy_info(proxy)
    assert actual is not None
    assert actual.type == ProxyType.SoladyCWIA
    assert actual.target == target


@geth_process_test
def test_old_cwia(project, geth_contract, owner, ethereum):
    target = geth_contract.address
    factory = owner.deploy(project.Template)
    tx = factory.clone2(target, b"\x00", sender=owner)
    actual = ethereum.get_proxy_info(tx.return_value)
    assert actual is not None
    assert actual.type == ProxyType.OldCWIA
    assert actual.target == target


@geth_process_test
def test_vyper_forwarder(project, geth_contract, owner, ethereum):
    target = geth_contract.address
    factory = owner.deploy(project.VyperFactory)
    tx = factory.create_proxy(target, sender=owner)
    actual = ethereum.get_proxy_info(tx.return_value)
    assert actual is not None
    assert actual.type == ProxyType.Minimal
    assert actual.target == target


@geth_process_test
def test_vyper(project, geth_contract, owner, ethereum):
    target = geth_contract.address
    addr = target[2:]
    runtime = f"366000600037611000600036600073{addr}5af4602c57600080fd5b6110006000f3"
    deployer = owner.deploy(project.RawDeployer)
    proxy = _deploy_runtime(owner, deployer, bytes.fromhex(runtime))
    actual = ethereum.get_proxy_info(proxy)
    assert actual is not None
    assert actual.type == ProxyType.Vyper
    assert actual.target == target


@geth_process_test
def test_vyper_beta(project, geth_contract, owner, ethereum):
    target = geth_contract.address
    addr = target[2:]
    runtime = f"366000600037611000600036600073{addr}5af41558576110006000f3"
    deployer = owner.deploy(project.RawDeployer)
    proxy = _deploy_runtime(owner, deployer, bytes.fromhex(runtime))
    actual = ethereum.get_proxy_info(proxy)
    assert actual is not None
    assert actual.type == ProxyType.VyperBeta
    assert actual.target == target


@geth_process_test
def test_zero_age(project, geth_contract, owner, ethereum):
    target = geth_contract.address
    addr = target[2:]
    runtime = f"3d3d3d3d363d3d37363d73{addr}5af43d3d93803e602a57fd5bf3"
    deployer = owner.deploy(project.RawDeployer)
    proxy = _deploy_runtime(owner, deployer, bytes.fromhex(runtime))
    actual = ethereum.get_proxy_info(proxy)
    assert actual is not None
    assert actual.type == ProxyType.ZeroAge
    assert actual.target == target


@geth_process_test
def test_sudoswap_cwia(project, geth_contract, owner, ethereum):
    target = geth_contract.address
    factory = owner.deploy(project.SudoswapCWIAFactory)
    tx = factory.deploycloneERC721ETHPair(target, 0, 0, 0, 0, 0, sender=owner)
    actual = ethereum.get_proxy_info(tx.return_value)
    assert actual is not None
    assert actual.type == ProxyType.SudoswapCWIA
    assert actual.target == target


@geth_process_test
def test_splits_cwia(project, geth_contract, owner, ethereum):
    target = geth_contract.address
    factory = owner.deploy(project.SplitsCloneFactory, target)
    tx = factory.createClone(0, 0, 0, 0, sender=owner)
    actual = ethereum.get_proxy_info(tx.return_value)
    assert actual is not None
    assert actual.type == ProxyType.SplitsCWIA
    assert actual.target == target


@geth_process_test
def test_splits_cwia_legacy(project, geth_contract, owner, ethereum):
    target = geth_contract.address
    addr = target[2:]
    runtime = (
        "36602f57343d527f9e4ac34f21c619cefc926c8bd93b54bf5a39c7ab2127a895af1cc0691d7e3dff"
        "60203da13d3df35b3d3d3d3d363d3d376100006067363936610000013d73"
        f"{addr}"
        "5af43d3d93803e606557fd5bf3"
    )
    deployer = owner.deploy(project.RawDeployer)
    proxy = _deploy_runtime(owner, deployer, bytes.fromhex(runtime))
    actual = ethereum.get_proxy_info(proxy)
    assert actual is not None
    assert actual.type == ProxyType.SplitsCWIA
    assert actual.target == target


@geth_process_test
def test_sequence(project, geth_contract, owner, ethereum):
    target = geth_contract.address
    factory = owner.deploy(project.SequenceFactory)
    tx = factory.deploy(target, b"\x00" * 32, sender=owner)
    actual = ethereum.get_proxy_info(tx.return_value)
    assert actual is not None
    assert actual.type == ProxyType.Sequence
    assert actual.target == target
