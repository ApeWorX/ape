from dataclasses import make_dataclass
from typing import Any, List, Tuple, Union

from ethpm_types.abi import ABIType, MethodABI


def parse_output_type(output_type: str) -> Union[str, Tuple]:
    if "(" not in output_type:
        return output_type

    # Strip off first opening parens
    output_type = output_type[1:]
    found_types: List[Union[str, Tuple]] = []

    while output_type:
        if output_type == ")":
            return tuple(found_types)

        elif output_type[0] == "(":
            # A tuple within the tuple
            end_index = output_type.index(")") + 1
            found_type = parse_output_type(output_type[:end_index])
            output_type = output_type[end_index:]
        else:
            found_type = output_type.split(",")[0].rstrip(")")
            end_index = len(found_type) + 1
            output_type = output_type[end_index:]

        if found_type:
            found_types.append(found_type)

    return tuple(found_types)


def parse_output_struct(abi: MethodABI, output_values: List) -> Any:
    default_name = f"{abi.name}_return"
    if output_is_struct(abi):
        # Handle structs.
        internal_type = abi.outputs[0].internalType
        if abi.outputs[0].name == "" and internal_type and "struct " in internal_type:
            name = internal_type.replace("struct ", "").split(".")[-1]
        else:
            name = abi.outputs[0].name or default_name

        return create_struct(
            name,
            abi.outputs[0].components,
            output_values[0],
        )

    elif output_is_named_tuple(abi, output_values):
        # Handle tuples. NOTE: unnamed output structs appear as tuples with named members
        return create_struct(default_name, abi.outputs, output_values)


def output_is_struct(abi: MethodABI) -> bool:
    return (
        len(abi.outputs) == 1
        and abi.outputs[0].components
        and all(c.name != "" for c in abi.outputs[0].components)
    )


def output_is_named_tuple(abi: MethodABI, output_values: List) -> bool:
    return all(o.name for o in abi.outputs) and len(output_values) > 1


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
