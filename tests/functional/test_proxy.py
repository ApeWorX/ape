from typing import TYPE_CHECKING

from eth_pydantic_types import HexBytes

from ape_ethereum.proxies import ProxyType
from ape_ethereum.utils import strip_compiler_metadata, strip_push_data
from ape_test.provider import LocalProvider

if TYPE_CHECKING:
    from ape.types import AddressType, BlockID

"""
NOTE: Most proxy tests are in `geth/test_proxy.py`.
"""


def test_strip_compiler_metadata_solidity():
    metadata = b"\xa2\x64ipfs\x58\x22\x12\x20" + (b"\x01" * 32) + b"\x64solc" + b"\x43\x00\x08\x12"
    bytecode = b"\x00\xf4" + metadata + len(metadata).to_bytes(2, "big")

    assert strip_compiler_metadata(bytecode) == b"\x00\xf4"


def test_strip_compiler_metadata_vyper():
    metadata = b"\xa1\x65vyper\x83\x00\x03\x09"
    bytecode = b"\x00\xf4" + metadata + len(metadata).to_bytes(2, "big")

    assert strip_compiler_metadata(bytecode) == b"\x00\xf4"


def test_strip_compiler_metadata_leaves_non_metadata():
    bytecode = bytes.fromhex("00a165627a7a72305820f4")

    assert strip_compiler_metadata(bytecode) == bytecode


def test_strip_compiler_metadata_leaves_unknown_cbor_tail():
    tail = b"\xa1\x63foo\x01"
    bytecode = b"\x00\xf4" + tail + len(tail).to_bytes(2, "big")

    assert strip_compiler_metadata(bytecode) == bytecode


def test_strip_push_data():
    assert strip_push_data(bytes.fromhex("61f4ff5ff4")) == bytes.fromhex("615ff4")


def test_composed_bytecode_strippers_ignore_push_data_and_compiler_metadata():
    metadata = b"\xa1\x65vyper\x83\x00\x03\x09"
    bytecode = b"\x00" + metadata + len(metadata).to_bytes(2, "big")

    assert 0xF4 in strip_push_data(strip_compiler_metadata(b"\xf4"))
    assert 0xF4 not in strip_push_data(strip_compiler_metadata(bytes.fromhex("61f4ff")))
    assert 0xF4 not in strip_push_data(strip_compiler_metadata(bytecode))


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
            self, address: "AddressType", slot: int, block_id: "BlockID | None" = None
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
