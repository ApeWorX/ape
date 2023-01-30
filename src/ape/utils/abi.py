import re
from dataclasses import make_dataclass
from typing import Any, Dict, List, Optional, Tuple, Union

from eth_abi import decode, grammar
from eth_utils import decode_hex, to_checksum_address
from ethpm_types import HexBytes
from ethpm_types.abi import ABIType, ConstructorABI, EventABI, EventABIType, MethodABI

ARRAY_PATTERN = re.compile(r"[(*\w,? )]*\[\d*]")


def is_array(abi_type: Union[str, ABIType]) -> bool:
    """
    Returns ``True`` if the given type is a probably an array.

    Args:
        abi_type (Union[str, ABIType]): The type to check.

    Returns:
        bool
    """

    return ARRAY_PATTERN.match(str(abi_type)) is not None


def returns_array(abi: MethodABI) -> bool:
    """
    Returns ``True`` if the given method ABI likely returns an array.

    Args:
        abi (MethodABI): An ABI method.

    Returns:
        bool
    """

    return _is_array_return(abi.outputs)


def _is_array_return(outputs: List[ABIType]):
    return len(outputs) == 1 and is_array(outputs[0].type)


class StructParser:
    """
    A utility class responsible for parsing structs out of values.
    """

    def __init__(self, method_abi: Union[ConstructorABI, MethodABI]):
        self.abi = method_abi

    @property
    def default_name(self) -> str:
        """
        The default struct return name for unnamed structs.
        This value is also used for named tuples where the tuple does not have a name
        (but each item in the tuple does have a name).
        """
        name = self.abi.name if isinstance(self.abi, MethodABI) else "constructor"
        return f"{name}_return"

    def encode_input(self, values: Union[List, Tuple]) -> Any:
        """
        Convert dicts and other objects to struct inputs.

        Args:
            values (Union[List, Tuple]): A list of of input values.

        Returns:
            Any: The same input values only decoded into structs when applicable.
        """

        return [self._encode_input(ipt, v) for ipt, v in zip(self.abi.inputs, values)]

    def _encode_input(self, input_type, value):
        if (
            input_type.type == "tuple"
            and input_type.components
            and all(m.name for m in input_type.components)
            and not isinstance(value, tuple)
        ):
            if isinstance(value, dict):
                return tuple([value[m.name] for m in input_type.components])

            else:
                arg = [getattr(value, m.name) for m in input_type.components if m.name]
                return tuple(arg)

        elif (
            str(input_type.type).startswith("tuple[")
            and isinstance(value, (list, tuple))
            and len(input_type.components) > 0
        ):
            non_array_type_data = input_type.dict()
            non_array_type_data["type"] = "tuple"
            non_array_type = ABIType(**non_array_type_data)
            return [self._encode_input(non_array_type, v) for v in value]

        return value

    def decode_output(self, values: Union[List, Tuple]) -> Any:
        """
        Parse a list of output types and values into structs.
        Values are only altered when they are a struct.
        This method also handles structs within structs as well as arrays of structs.

        Args:
            values (Union[List, Tuple]): A list of of output values.

        Returns:
            Any: The same input values only decoded into structs when applicable.
        """

        return (
            self._decode_output(self.abi.outputs, values)
            if isinstance(self.abi, MethodABI)
            else None
        )

    def _decode_output(self, output_types: List[ABIType], values: Union[List, Tuple]):
        if is_struct(output_types):
            return_value = self._create_struct(output_types[0], values)
            return return_value

        elif is_named_tuple(output_types, values):
            # Handle tuples. NOTE: unnamed output structs appear as tuples with named members
            return create_struct(self.default_name, output_types, values)

        return_values: List = []
        has_array_return = _is_array_return(output_types)
        has_array_of_tuples_return = (
            has_array_return and len(output_types) == 1 and "tuple" in output_types[0].type
        )
        if has_array_return and not has_array_of_tuples_return:
            # Normal array
            return values

        elif has_array_of_tuples_return:
            item_type_str = str(output_types[0].type).split("[")[0]
            data = {**output_types[0].dict(), "type": item_type_str, "internalType": item_type_str}
            output_type = ABIType.parse_obj(data)

            if not values[0]:
                # Only returned an empty list.
                return_values.append([])

            else:
                for value in values[0]:
                    item = self._decode_output([output_type], [value])
                    return_values.append(item)

        else:
            for output_type, value in zip(output_types, values):
                if isinstance(value, (tuple, list)):
                    item_type_str = str(output_type.type).split("[")[0]

                    if item_type_str == "tuple":
                        item_type_data = {
                            **output_type.dict(),
                            "type": item_type_str,
                            "internalType": item_type_str,
                        }
                        item_type = ABIType.parse_obj(item_type_data)
                        parsed_item = self._decode_output([item_type], [value])

                        # If it's an empty dynamic array of structs, replace `None` with empty list
                        output_raw_type = output_type.type
                        if (
                            isinstance(output_raw_type, str)
                            and output_raw_type.endswith("[]")
                            and parsed_item is None
                        ):
                            parsed_item = []

                    else:
                        # Handle tuple of arrays
                        parsed_item = [v for v in value]

                    return_values.append(parsed_item)
                else:
                    return_values.append(value)

        return return_values

    def _create_struct(self, out_abi: ABIType, out_value) -> Optional[Any]:
        if not out_abi.components or not out_value[0]:
            # Likely an empty tuple or not a struct.
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
        for component, value in zip(components, values):
            if is_struct(component):
                new_value = self._create_struct(component, (value,))
                parsed_values.append(new_value)
            elif is_array(component.type) and "tuple" in component.type and component.components:
                new_value = [self._decode_output(component.components, v) for v in value]
                parsed_values.append(new_value)
            else:
                parsed_values.append(value)

        return parsed_values


def is_struct(outputs: Union[ABIType, List[ABIType]]) -> bool:
    """
    Returns ``True`` if the given output is a struct.
    """

    if not isinstance(outputs, (tuple, list)):
        outputs = [outputs]

    return (
        len(outputs) == 1
        and "[" not in outputs[0].type
        and outputs[0].components not in (None, [])
        and all(c.name != "" for c in outputs[0].components or [])
    )


def is_named_tuple(outputs: List[ABIType], output_values: Union[List, Tuple]) -> bool:
    """
    Returns ``True`` if the given output is a tuple where every item is named.
    """

    return all(o.name for o in outputs) and len(output_values) > 1


class Struct:
    """
    A class for contract return values using the struct data-structure.
    """

    def items(self) -> Dict:
        """Override"""
        return {}


def create_struct(
    name: str, types: List[ABIType], output_values: Union[List[Any], Tuple[Any, ...]]
) -> Any:
    """
    Create a dataclass representing an ABI struct that can be used as inputs or outputs.
    The struct properties can be accessed via ``.`` notation, as keys in a dictionary, or
    numeric tuple access.

    **NOTE**: This method assumes you already know the values to give to the struct
    properties.

    Args:
        name (str): The name of the struct.
        types (List[ABIType]: The types of values in the struct.
        output_values (List[Any]): The struct property values.

    Returns:
        Any: The struct dataclass.
    """

    def get_item(struct, index) -> Any:
        # NOTE: Allow struct to function as a tuple and dict as well
        struct_values = tuple(getattr(struct, field) for field in struct.__dataclass_fields__)
        if isinstance(index, str):
            return dict(zip(struct.__dataclass_fields__, struct_values))[index]

        return struct_values[index]

    def is_equal(struct, other) -> bool:
        _len = len(other)
        return _len == len(struct) and all([struct[i] == other[i] for i in range(_len)])

    def length(struct) -> int:
        return len(struct.__dataclass_fields__)

    def items(struct) -> List[Tuple]:
        return [(k, struct[k]) for k, v in struct.__dataclass_fields__.items()]

    struct_def = make_dataclass(
        name,
        # NOTE: Should never be "_{i}", but mypy complains and we need a unique value
        [m.name or f"_{i}" for i, m in enumerate(types)],
        namespace={"__getitem__": get_item, "__eq__": is_equal, "__len__": length, "items": items},
        bases=(Struct,),  # We set a base class for subclass checking elsewhere.
    )

    return struct_def(*output_values)


def is_dynamic_sized_type(abi_type: Union[ABIType, str]) -> bool:
    parsed = grammar.parse(str(abi_type))
    return parsed.is_dynamic


class LogInputABICollection:
    def __init__(self, abi: EventABI):
        self.abi = abi
        self.topic_abi_types = [i for i in abi.inputs if i.indexed]
        self.data_abi_types: List[EventABIType] = [i for i in abi.inputs if not i.indexed]

        names = [i.name for i in abi.inputs]
        if len(set(names)) < len(names):
            raise ValueError("duplicate names found in log input", abi)

    @property
    def event_name(self):
        return self.abi.name

    def decode(self, topics: List[str], data: str) -> Dict:
        decoded = {}
        for abi, topic_value in zip(self.topic_abi_types, topics[1:]):
            # reference types as indexed arguments are written as a hash
            # https://docs.soliditylang.org/en/v0.8.15/contracts.html#events
            abi_type = "bytes32" if is_dynamic_sized_type(abi.type) else abi.canonical_type
            value = decode([abi_type], decode_hex(topic_value))[0]
            decoded[abi.name] = self.decode_value(abi_type, value)

        data_abi_types = [abi.canonical_type for abi in self.data_abi_types]
        hex_data = decode_hex(data) if isinstance(data, str) else data
        data_values = decode(data_abi_types, hex_data)

        for abi, value in zip(self.data_abi_types, data_values):
            decoded[abi.name] = self.decode_value(abi.canonical_type, value)

        return decoded

    def decode_value(self, abi_type, value):
        if abi_type == "address":
            return to_checksum_address(value)
        elif abi_type == "bytes32":
            return HexBytes(value)

        return value
