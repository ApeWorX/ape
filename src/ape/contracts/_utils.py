from typing import Dict, Iterator, List, Union

from eth_abi import grammar
from eth_utils.abi import collapse_if_tuple
from ethpm_types.abi import EventABI, EventABIType


class LogInputABICollection:
    def __init__(self, abi: EventABI, values: List[EventABIType]):
        self.abi = abi
        self.values = values

    @property
    def names(self) -> List[str]:
        return [abi.name for abi in self.values if abi.name]

    @property
    def normalized_values(self) -> List[Dict]:
        return [abi.dict() for abi in self.values]

    @property
    def types(self) -> List[Union[str, Dict]]:
        return [t for t in _get_event_abi_types(self.normalized_values)]


def _get_event_abi_types(abi_inputs: List[Dict]) -> Iterator[Union[str, Dict]]:
    for abi_input in abi_inputs:
        abi_type = grammar.parse(abi_input["type"])
        if abi_type.is_dynamic:
            yield "bytes32"
        else:
            yield collapse_if_tuple(abi_input)


__all__ = ["LogInputABICollection"]
