from dataclasses import make_dataclass
from typing import Any, List, Optional, Union

from ethpm_types.abi import ABIType, MethodABI


class StructParser:
    def __init__(self, method_abi: MethodABI):
        self.method_abi = method_abi

    @property
    def default_name(self) -> str:
        return f"{self.method_abi.name}_return"

    def parse(self, output_types: List[ABIType], values: List) -> Any:
        if is_struct(output_types):
            return self._create_struct(output_types[0], values)

        elif is_named_tuple(output_types, values):
            # Handle tuples. NOTE: unnamed output structs appear as tuples with named members
            return create_struct(self.default_name, output_types, values)

    def _create_struct(self, out_abi: ABIType, out_value) -> Optional[Any]:
        if not out_abi.components:
            return None

        internal_type = out_abi.internalType
        if out_abi.name == "" and internal_type and "struct " in internal_type:
            name = internal_type.replace("struct ", "").split(".")[-1]
        else:
            name = out_abi.name or self.default_name

        components = self._parse_components(out_abi.components, out_value[0])
        result = create_struct(
            name,
            out_abi.components,
            components,
        )
        return result

    def _parse_components(self, components: List[ABIType], values) -> List:
        parsed_values = []
        for component, val in zip(components, values):
            new_val = self._create_struct(component, (val,)) if is_struct(component) else val
            parsed_values.append(new_val)

        return parsed_values


def is_struct(outputs: Union[ABIType, List[ABIType]]) -> bool:
    if not isinstance(outputs, (tuple, list)):
        outputs = [outputs]

    return (
        len(outputs) == 1
        and outputs[0].components not in (None, [])
        and all(c.name != "" for c in outputs[0].components or [])
    )


def is_named_tuple(outputs: List[ABIType], output_values: List) -> bool:
    return all(o.name for o in outputs) and len(output_values) > 1


def create_struct(name: str, types: List[ABIType], output_values: List[Any]) -> Any:
    def get_item(struct, index) -> Any:
        # NOTE: Allow struct to function as a tuple and dict as well
        struct_values = tuple(getattr(struct, field) for field in struct.__dataclass_fields__)
        if isinstance(index, str):
            return dict(zip(struct.__dataclass_fields__, struct_values))[index]

        return struct_values[index]

    def is_equal(struct, other) -> bool:
        if not isinstance(other, tuple):
            return super().__eq__(other)  # type: ignore

        _len = len(other)
        return _len == len(struct) and all([struct[i] == other[i] for i in range(_len)])

    def length(struct) -> int:
        return len(struct.__dataclass_fields__)

    struct_def = make_dataclass(
        name,
        # NOTE: Should never be "_{i}", but mypy complains and we need a unique value
        [m.name or f"_{i}" for i, m in enumerate(types)],
        namespace={"__getitem__": get_item, "__eq__": is_equal, "__len__": length},
    )

    return struct_def(*output_values)
