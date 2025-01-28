import pytest

from ape.exceptions import ContractNotFoundError
from tests.conftest import geth_process_test


@geth_process_test
def test_get_proxy_from_explorer(
    mock_explorer,
    create_mock_sepolia,
    safe_proxy_container,
    geth_account,
    vyper_contract_container,
    geth_provider,
    chain,
):
    """
    Simulated when you get a contract from Etherscan for the first time
    but that contract is a proxy. We expect both proxy and target ABIs
    to be cached under the proxy's address.
    """
    target_contract = geth_account.deploy(vyper_contract_container, 10011339315)
    proxy_contract = geth_account.deploy(safe_proxy_container, target_contract.address)

    # Ensure both of these are not cached so we have to rely on our fake explorer.
    del chain.contracts[target_contract.address]
    del chain.contracts[proxy_contract.address]
    # Sanity check.
    with pytest.raises(ContractNotFoundError):
        _ = chain.contracts.instance_at(proxy_contract.address)

    def get_contract_type(address, *args, **kwargs):
        # Mock etherscan backend.
        if address == target_contract.address:
            return target_contract.contract_type
        elif address == proxy_contract.address:
            return proxy_contract.contract_type

        raise ValueError("Fake explorer only knows about proxy and target contracts.")

    with create_mock_sepolia() as network:
        # Set up our network to use our fake explorer.
        mock_explorer.get_contract_type.side_effect = get_contract_type
        network.__dict__["explorer"] = mock_explorer

        # Typical flow: user attempts to get an un-cached contract type from Etherscan.
        # That contract may be a proxy, in which case we should get a type
        # w/ both proxy ABIs and the target ABIs.
        contract_from_explorer = chain.contracts.instance_at(proxy_contract.address)

        network.__dict__.pop("explorer", None)

        # Ensure we can call proxy methods!
        assert contract_from_explorer.masterCopy  # No attr error!

        # Ensure we can call target methods!
        assert contract_from_explorer.myNumber  # No attr error!
