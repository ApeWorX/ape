"""Unit tests for ContractEvent slice access with a fake log iterator."""

from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from ethpm_types import EventABI

from ape.contracts.base import ContractEvent
from ape.types.events import MockContractLog


def _make_event(fake_logs):
    provider = MagicMock()
    provider.get_contract_logs = MagicMock(return_value=iter(fake_logs))

    abi = EventABI(
        name="NumberChange",
        type="event",
        inputs=[],
    )
    contract = MagicMock()
    contract.address = None

    event = ContractEvent.model_construct(contract=contract, abi=abi)
    return event, provider


@pytest.fixture
def fake_logs():
    return [
        MockContractLog(event_name="NumberChange", newNum=1),
        MockContractLog(event_name="NumberChange", newNum=2),
        MockContractLog(event_name="NumberChange", newNum=3),
    ]


@pytest.mark.parametrize(
    "slice_obj",
    [
        slice(-2, None),
        slice(None, -1),
        slice(None, None, -1),
    ],
)
def test_contract_event_slice_negative_indices(fake_logs, slice_obj):
    """Slicing with negative bounds must match list slice semantics on the same logs."""
    event, provider = _make_event(fake_logs)
    expected = fake_logs[slice_obj]

    with patch.object(ContractEvent, "provider", new_callable=PropertyMock, return_value=provider):
        result = event[slice_obj]

    assert [log.event_name for log in result] == [log.event_name for log in expected]
    assert len(result) == len(expected)