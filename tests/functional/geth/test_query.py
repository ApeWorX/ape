from typing import List, Tuple

from ape.exceptions import ChainError
from tests.conftest import geth_process_test


@geth_process_test
def test_get_contract_creation_receipts(mock_geth, geth_contract, chain, networks, geth_provider):
    geth_provider.__dict__["explorer"] = None
    provider = networks.active_provider
    networks.active_provider = mock_geth
    mock_geth._web3.eth.get_block.side_effect = (
        lambda bid, *args, **kwargs: geth_provider.get_block(bid)
    )

    try:
        mock_geth._web3.eth.get_code.return_value = b"123"

        # NOTE: Due to mocks, this next part may not actually find the contract.
        #  but that is ok but we mostly want to make sure it tries OTS. There
        #  are other tests for the brute-force logic.
        try:
            next(chain.contracts.get_creation_receipt(geth_contract.address), None)
        except ChainError:
            pass

        # Ensure we tried using OTS.
        actual = mock_geth._web3.provider.make_request.call_args
        expected: Tuple[str, List] = ("ots_getApiLevel", [])
        assert any(arguments == expected for arguments in actual)

    finally:
        networks.active_provider = provider
