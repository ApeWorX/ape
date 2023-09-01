from ape_ethereum.proxies import ProxyType
from tests.conftest import geth_process_test


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
def test_beacon_proxy(ethereum, beacon_proxy, geth_provider, geth_vyper_contract):
    """
    NOTE: Geth is used here because EthTester does not implement getting storage slots.
    """
    actual = ethereum.get_proxy_info(beacon_proxy.address)
    assert actual is not None
    assert actual.type == ProxyType.Beacon
    assert actual.target == geth_vyper_contract.address
