from typing import NamedTuple

import pytest
from eth_pydantic_types import HexBytes
from ethpm_types import ContractType

from ape.exceptions import APINotImplementedError
from ape_ethereum.multicall import Call
from ape_ethereum.multicall.constants import MULTICALL3_ADDRESS, MULTICALL3_CONTRACT_TYPE
from ape_ethereum.multicall.exceptions import UnsupportedChainError

RETURNDATA = HexBytes("0x4a821464")


class ReturnData(NamedTuple):
    success: bool
    returnData: bytes


RETURNDATA_PARAMS = {
    "result_ok": (ReturnData(True, RETURNDATA), RETURNDATA),
    "result_fail": (ReturnData(False, RETURNDATA), None),
}


@pytest.fixture(scope="module")
def undeployed_multicall(chain):
    # NOTE: Still has the ability to decode/encode inputs.
    return chain.contracts.instance_at(
        MULTICALL3_ADDRESS,
        contract_type=ContractType.model_validate(MULTICALL3_CONTRACT_TYPE),
    )


@pytest.fixture(scope="module")
def aggregate3(undeployed_multicall):
    # NOTE: Avoid `__getattr__` call as it requires a real contract.
    return undeployed_multicall._mutable_methods_["aggregate3"]


def test_inject_raises_not_implemented():
    with pytest.raises(APINotImplementedError):
        Call.inject()


def test_unsupported_chain(call_handler_with_struct_input, struct_input_for_call):
    call = Call()
    call.add(call_handler_with_struct_input, *struct_input_for_call, allowFailure=True)

    # The local test chain doesn't have the multicall contracts.
    with pytest.raises(UnsupportedChainError):
        next(call())


def test_aggregate3_input(
    aggregate3,
    call_handler_with_struct_input,
    struct_input_for_call,
    vyper_contract_instance,
):
    call = Call()

    # Use a real contract here so the target encoding works.
    call_handler_with_struct_input.contract = vyper_contract_instance

    call.add(call_handler_with_struct_input, *struct_input_for_call)
    actual = aggregate3.encode_input(call.calls)
    assert isinstance(actual, HexBytes)


@pytest.mark.parametrize("returndata_key", RETURNDATA_PARAMS)
def test_returndata(returndata_key):
    result, output = RETURNDATA_PARAMS[returndata_key]
    call = Call()
    call._result = [result]  # type: ignore
    assert call.returnData[0] == output


def test_add_overloaded_records_the_encoded_overload(chain, eth_tester_provider):
    # The recorded ABI decodes the return data, so it has to be the same overload that
    # encoded the calldata. Both go through type-aware selection or neither does.
    # bytes[] first so that count-only selection would land on the uint256 overload and
    # disagree with the calldata.
    abi = [
        {
            "type": "function",
            "name": "getUpdateFee",
            "stateMutability": "view",
            "inputs": [{"name": "updateData", "type": "bytes[]"}],
            "outputs": [{"name": "", "type": "uint256"}],
        },
        {
            "type": "function",
            "name": "getUpdateFee",
            "stateMutability": "view",
            "inputs": [{"name": "updateDataSize", "type": "uint256"}],
            "outputs": [{"name": "", "type": "uint256"}],
        },
    ]
    contract = chain.contracts.instance_at(
        "0x8888888888888888888888888888888888888888",
        abi=abi,
        detect_proxy=False,
        fetch_from_explorer=False,
        fetch_from_disk=False,
    )
    call = Call()

    call.add(contract.getUpdateFee, [])

    ecosystem = eth_tester_provider.network.ecosystem
    assert call.abis[0].inputs[0].canonical_type == "bytes[]"
    assert call.calls[0]["callData"][:4] == ecosystem.get_method_selector(call.abis[0])
