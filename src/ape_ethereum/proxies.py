from enum import IntEnum

from ethpm_types import ContractType
from lazyasd import LazyObject  # type: ignore

from ape.api.networks import ProxyInfoAPI
from ape.contracts import ContractContainer

MINIMAL_PROXY_BYTES = (
    "0x3d602d80600a3d3981f3363d3d373d3d3d363d73"
    "bebebebebebebebebebebebebebebebebebebebe5af43d82803e903d91602b57fd5bf3"
)


class ProxyType(IntEnum):
    Minimal = 0  # eip-1167 minimal proxy contract
    Standard = 1  # eip-1967 standard proxy storage slots
    Beacon = 2  # eip-1967 beacon proxy
    UUPS = 3  # # eip-1822 universal upgradeable proxy standard
    Vyper = 4  # vyper <0.2.9 create_forwarder_to
    Clones = 5  # 0xsplits clones
    GnosisSafe = 6
    OpenZeppelin = 7  # openzeppelin upgradeability proxy
    Delegate = 8  # eip-897 delegate proxy
    ZeroAge = 9  # a more-minimal proxy
    SoladyPush0 = 10  # solady push0 minimal proxy


class ProxyInfo(ProxyInfoAPI):
    type: ProxyType


def _make_minimal_proxy() -> ContractContainer:
    bytecode = {"bytecode": MINIMAL_PROXY_BYTES}
    contract_type = ContractType(abi=[], deploymentBytecode=bytecode)
    return ContractContainer(contract_type=contract_type)


minimal_proxy = LazyObject(_make_minimal_proxy, globals(), "minimal_proxy")
