from enum import IntEnum, auto
from typing import cast

from eth_pydantic_types.hex import HexStr
from ethpm_types import ContractType, MethodABI
from ethpm_types.abi import ABIType
from lazyasd import LazyObject  # type: ignore

from ape.api.networks import ProxyInfoAPI
from ape.contracts import ContractContainer

MINIMAL_PROXY_TARGET_PLACEHOLDER = "bebebebebebebebebebebebebebebebebebebebe"
MINIMAL_PROXY_BYTES = (
    "0x3d602d80600a3d3981f3363d3d373d3d3d363d73"
    f"{MINIMAL_PROXY_TARGET_PLACEHOLDER}5af43d82803e903d91602b57fd5bf3"
)


class ProxyType(IntEnum):
    # https://eips.ethereum.org/EIPS/eip-1167
    Minimal = auto()  # eip-1167 minimal proxy contract

    # https://eips.ethereum.org/EIPS/eip-1967
    Standard = auto()  # eip-1967 standard proxy storage slots
    Beacon = auto()  # eip-1967 beacon proxy

    # https://eips.ethereum.org/EIPS/eip-1822
    UUPS = auto()  # # eip-1822 universal upgradeable proxy standard

    # https://github.com/vyperlang/vyper/blob/v0.2.8/vyper/functions/functions.py#L1428
    Vyper = auto()  # vyper <0.2.9 create_forwarder_to
    # https://github.com/vyperlang/vyper/blob/v0.1.0-beta.4/vyper/functions/functions.py#L633
    VyperBeta = auto()  # vyper 0.1-beta

    # https://github.com/0xSplits/splits-contracts/blob/main/contracts/libraries/Clones.sol
    Clones = auto()  # 0xsplits clones

    # https://github.com/safe-global/safe-contracts/blob/main/contracts/proxies/SafeProxy.sol
    GnosisSafe = auto()

    # https://github.com/OpenZeppelin/openzeppelin-labs/blob/master/initializer_contracts/contracts/UpgradeabilityProxy.sol
    OpenZeppelin = auto()  # openzeppelin upgradeability proxy

    # https://eips.ethereum.org/EIPS/eip-897
    Delegate = auto()  # eip-897 delegate proxy

    # https://medium.com/coinmonks/the-more-minimal-proxy-5756ae08ee48
    ZeroAge = auto()  # a more-minimal proxy

    # https://github.com/wighawag/clones-with-immutable-args/blob/master/src/ClonesWithImmutableArgs.sol
    CWIA = auto()  # clones with immutable args
    # https://github.com/wighawag/clones-with-immutable-args/blob/bb93749/src/ClonesWithCallData.sol
    OldCWIA = auto()

    # https://github.com/Vectorized/solady/blob/main/src/utils/LibClone.sol
    SoladyPush0 = auto()  # solady push0 minimal proxy
    SoladyCWIA = auto()  # clones with immutable args with a receive method

    # https://github.com/sudoswap/lssvm2/blob/main/src/lib/LSSVMPairCloner.sol
    SudoswapCWIA = auto()  # a variant used in sudoswap

    # https://github.com/0xSplits/clones-with-immutable-args/blob/864a87a/src/ClonesWithImmutableArgs.sol
    SplitsCWIA = auto()  # a variant used in 0xsplits

    # https://github.com/0xsequence/wallet-contracts/blob/master/contracts/Wallet.sol
    Sequence = auto()


class ProxyInfo(ProxyInfoAPI):
    type: ProxyType


MASTER_COPY_ABI = MethodABI(
    type="function",
    name="masterCopy",
    stateMutability="view",
    outputs=[ABIType(type="address")],
)
PROXY_TYPE_ABI = MethodABI(
    type="function",
    name="proxyType",
    stateMutability="view",
    outputs=[ABIType(type="uint256")],
)
IMPLEMENTATION_ABI = MethodABI(
    type="function",
    name="implementation",
    stateMutability="view",
    outputs=[ABIType(type="address")],
)


def _make_minimal_proxy(address: str = MINIMAL_PROXY_TARGET_PLACEHOLDER) -> ContractContainer:
    address = address.replace("0x", "")
    code = cast(HexStr, MINIMAL_PROXY_BYTES.replace(MINIMAL_PROXY_TARGET_PLACEHOLDER, address))
    bytecode = {"bytecode": code}
    contract_type = ContractType(abi=[], deploymentBytecode=bytecode)
    return ContractContainer(contract_type=contract_type)


minimal_proxy = LazyObject(_make_minimal_proxy, globals(), "minimal_proxy")
