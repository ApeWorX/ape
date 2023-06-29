import pytest
from ethpm_types import HexBytes

from ape.contracts import ContractContainer
from ape_ethereum.proxies import ProxyType
from ape_ethereum.proxies import minimal_proxy as minimal_proxy_container
from tests.conftest import geth_process_test


@pytest.fixture
def minimal_proxy(owner):
    return owner.deploy(minimal_proxy_container)


@pytest.fixture
def standard_proxy(owner, get_contract_type, geth_vyper_contract):
    _type = get_contract_type("eip1967")
    contract = ContractContainer(_type)
    target = geth_vyper_contract.address
    return owner.deploy(contract, target, HexBytes(""))


@pytest.fixture
def beacon(owner, get_contract_type, geth_provider, vyper_contract_instance):
    _type = get_contract_type("beacon")
    contract = ContractContainer(_type)
    return owner.deploy(contract, vyper_contract_instance)


@pytest.fixture
def beacon_proxy(owner, get_contract_type, beacon, geth_provider):
    _type = get_contract_type("beacon_proxy")
    contract = ContractContainer(_type)
    return owner.deploy(contract, beacon, HexBytes(""))


def test_minimal_proxy(ethereum, minimal_proxy):
    actual = ethereum.get_proxy_info(minimal_proxy.address)
    assert actual is not None
    assert actual.type == ProxyType.Minimal
    # It is the placeholder value still.
    assert actual.target == "0xBEbeBeBEbeBebeBeBEBEbebEBeBeBebeBeBebebe"


@geth_process_test
def test_standard_proxy(ethereum, standard_proxy, geth_provider, geth_vyper_contract):
    """
    NOTE: Geth is used here because EthTester does not implement getting storage slots.
    """
    actual = ethereum.get_proxy_info(standard_proxy.address)
    assert actual is not None
    assert actual.type == ProxyType.Standard
    assert actual.target == geth_vyper_contract.address


@geth_process_test
def test_beacon_proxy(ethereum, beacon_proxy, geth_provider, vyper_contract_instance):
    """
    NOTE: Geth is used here because EthTester does not implement getting storage slots.
    """
    actual = ethereum.get_proxy_info(beacon_proxy.address)
    assert actual is not None
    assert actual.type == ProxyType.Beacon
    assert actual.target == vyper_contract_instance.address
