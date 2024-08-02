import re
from collections.abc import Sequence
from dataclasses import make_dataclass
from typing import Any, Optional, Union

from eth_abi import decode, grammar
from eth_abi.exceptions import DecodingError, InsufficientDataBytes
from eth_pydantic_types import HexBytes
from eth_utils import decode_hex
from ethpm_types.abi import ABIType, ConstructorABI, EventABI, EventABIType, MethodABI

from ape.logging import logger

ARRAY_PATTERN = re.compile(r"[(*\w,? )]*\[\d*]")
NATSPEC_KEY_PATTERN = re.compile(r"(@\w+)")


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


def _is_array_return(outputs: Sequence[ABIType]):
    return len(outputs) == 1 and is_array(outputs[0].type)


class StructParser:
    """
    A utility class responsible for parsing structs out of values.
    """

    def __init__(self, method_abi: Union[ConstructorABI, MethodABI, EventABI]):
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

    def encode_input(self, values: Union[list, tuple, dict]) -> Any:
        """
        Convert dicts and other objects to struct inputs.

        Args:
            values (Union[list, tuple]): A list of of input values.

        Returns:
            Any: The same input values only decoded into structs when applicable.
        """

        return [self._encode(ipt, v) for ipt, v in zip(self.abi.inputs, values)]

    def decode_input(self, values: Union[Sequence, dict[str, Any]]) -> Any:
        return (
            self._decode(self.abi.inputs, values)
            if isinstance(self.abi, (EventABI, MethodABI))
            else None
        )

    def _encode(self, _type: ABIType, value: Any):
        if (
            _type.type == "tuple"
            and _type.components
            and all(m.name for m in _type.components)
            and not isinstance(value, tuple)
        ):
            if isinstance(value, dict):
                return tuple(
                    (
                        self._encode(m, value[m.name])
                        if isinstance(value[m.name], dict)
                        else value[m.name]
                    )
                    for m in _type.components
                )

            elif isinstance(value, (list, tuple)):
                # NOTE: Args must be passed in correct order.
                return tuple(value)

            else:
                arg = [getattr(value, m.name) for m in _type.components if m.name]
                return tuple(arg)

        elif (
            str(_type.type).startswith("tuple[")
            and isinstance(value, (list, tuple))
            and len(_type.components or []) > 0
        ):
            non_array_type_data = _type.model_dump()
            non_array_type_data["type"] = "tuple"
            non_array_type = ABIType(**non_array_type_data)
            return [self._encode(non_array_type, v) for v in value]

        return value

    def decode_output(self, values: Union[list, tuple]) -> Any:
        """
        Parse a list of output types and values into structs.
        Values are only altered when they are a struct.
        This method also handles structs within structs as well as arrays of structs.

        Args:
            values (Union[list, tuple]): A list of of output values.

        Returns:
            Any: The same input values only decoded into structs when applicable.
        """

        return self._decode(self.abi.outputs, values) if isinstance(self.abi, MethodABI) else None

    def _decode(
        self,
        _types: Union[Sequence[ABIType]],
        values: Union[Sequence, dict[str, Any]],
    ):
        if is_struct(_types):
            return self._create_struct(_types[0], values)

        elif isinstance(values, (list, tuple)) and is_named_tuple(_types, values):
            # Handle tuples. NOTE: unnamed output structs appear as tuples with named members
            return create_struct(self.default_name, _types, values)

        return_values: list = []
        has_array_return = _is_array_return(_types)
        has_array_of_tuples_return = (
            has_array_return and len(_types) == 1 and "tuple" in _types[0].type
        )
        if has_array_return and not has_array_of_tuples_return:
            # Normal array
            return values

        elif has_array_of_tuples_return:
            item_type_str = str(_types[0].type).partition("[")[0]
            data = {
                **_types[0].model_dump(),
                "type": item_type_str,
                "internalType": item_type_str,
            }
            output_type = ABIType.model_validate(data)

            if isinstance(values, (list, tuple)) and not values[0]:
                # Only returned an empty list.
                return_values.append([])

            elif isinstance(values, (list, tuple)):
                for value in values[0]:
                    item = self._decode([output_type], [value])
                    return_values.append(item)

        else:
            for output_type, value in zip(_types, values):
                if isinstance(value, (tuple, list)):
                    item_type_str = str(output_type.type).partition("[")[0]
                    if item_type_str == "tuple":
                        # Either an array of structs or nested structs.
                        item_type_data = {
                            **output_type.model_dump(),
                            "type": item_type_str,
                            "internalType": item_type_str,
                        }
                        item_type = ABIType.model_validate(item_type_data)

                        if is_struct(output_type):
                            parsed_item = self._decode([item_type], [value])
                        else:
                            # Is array of structs.
                            parsed_item = [self._decode([item_type], [v]) for v in value]

                        # If it's an empty dynamic array of structs, replace `None` with empty list
                        output_raw_type = output_type.type
                        if (
                            isinstance(output_raw_type, str)
                            and output_raw_type.endswith("[]")
                            and parsed_item is None
                        ):
                            parsed_item = []

                    else:
                        parsed_item = [HexBytes(v) if isinstance(v, bytes) else v for v in value]

                    return_values.append(parsed_item)

                else:
                    return_values.append(value)

        return return_values

    def _create_struct(self, out_abi: ABIType, out_value: Any) -> Optional[Any]:
        if not out_abi.components or not out_value[0]:
            # Likely an empty tuple or not a struct.
            return None

        internal_type = out_abi.internal_type
        if out_abi.name == "" and internal_type and "struct " in internal_type:
            name = internal_type.replace("struct ", "").split(".")[-1]
        else:
            name = out_abi.name or self.default_name

        components = self._parse_components(out_abi.components, out_value[0])
        return create_struct(
            name,
            out_abi.components,
            components,
        )

    def _parse_components(self, components: list[ABIType], values) -> list:
        parsed_values = []
        for component, value in zip(components, values):
            if is_struct(component):
                new_value = self._create_struct(component, (value,))
                parsed_values.append(new_value)
            elif is_array(component.type) and "tuple" in component.type and component.components:
                new_value = [self._decode(component.components, v) for v in value]
                parsed_values.append(new_value)
            else:
                parsed_values.append(value)

        return parsed_values


def is_struct(outputs: Union[ABIType, Sequence[ABIType]]) -> bool:
    """
    Returns ``True`` if the given output is a struct.
    """

    outputs_seq = outputs if isinstance(outputs, (tuple, list)) else [outputs]
    return (
        len(outputs_seq) == 1
        and "[" not in outputs_seq[0].type
        and outputs_seq[0].components not in (None, [])
        and all(c.name != "" for c in outputs_seq[0].components or [])
    )


def is_named_tuple(outputs: Sequence[ABIType], output_values: Sequence) -> bool:
    """
    Returns ``True`` if the given output is a tuple where every item is named.
    """

    return all(o.name for o in outputs) and len(output_values) > 1


class Struct:
    """
    A class for contract return values using the struct data-structure.
    """

    def items(self) -> dict:
        """Override"""
        return {}

    def __setitem__(self, key, value):
        """Override"""
        pass


def create_struct(name: str, types: Sequence[ABIType], output_values: Sequence) -> Any:
    """
    Create a dataclass representing an ABI struct that can be used as inputs or outputs.
    The struct properties can be accessed via ``.`` notation, as keys in a dictionary, or
    numeric tuple access.

    **NOTE**: This method assumes you already know the values to give to the struct
    properties.

    Args:
        name (str): The name of the struct.
        types (list[ABIType]: The types of values in the struct.
        output_values (list[Any]): The struct property values.

    Returns:
        Any: The struct dataclass.
    """

    def get_item(struct, key) -> Any:
        # NOTE: Allow struct to function as a tuple and dict as well
        struct_values = tuple(getattr(struct, field) for field in struct.__dataclass_fields__)
        if isinstance(key, str):
            return dict(zip(struct.__dataclass_fields__, struct_values))[key]

        return struct_values[key]

    def set_item(struct, key, value):
        if isinstance(key, str):
            setattr(struct, key, value)
        else:
            struct_values = tuple(getattr(struct, field) for field in struct.__dataclass_fields__)
            field_to_set = struct_values[key]
            setattr(struct, field_to_set, value)

    def contains(struct, key):
        return key in struct.__dataclass_fields__

    def is_equal(struct, other) -> bool:
        if not hasattr(other, "__len__"):
            return NotImplemented

        _len = len(other)
        if _len != len(struct):
            return False

        if hasattr(other, "items"):
            # Struct or dictionary.
            for key, value in other.items():
                if key not in struct:
                    # Different object.
                    return False

                if struct[key] != value:
                    # Mismatched properties.
                    return False

            # Both objects represent the same struct.
            return True

        elif isinstance(other, (list, tuple)):
            # Allows comparing structs with sequence types.
            # NOTE: The order of the expected sequence matters!

            for itm1, itm2 in zip(struct.values(), other):
                if itm1 != itm2:
                    return False

            return True

        else:
            return NotImplemented

    def length(struct) -> int:
        return len(struct.__dataclass_fields__)

    def items(struct) -> list[tuple]:
        return [(k, struct[k]) for k, v in struct.__dataclass_fields__.items()]

    def values(struct) -> list[Any]:
        return [x[1] for x in struct.items()]

    def reduce(struct) -> tuple:
        return (create_struct, (name, types, output_values))

    # NOTE: Should never be "_{i}", but mypy complains and we need a unique value
    properties = [m.name or f"_{i}" for i, m in enumerate(types)]
    methods = {
        "__eq__": is_equal,
        "__getitem__": get_item,
        "__setitem__": set_item,
        "__contains__": contains,
        "__len__": length,
        "__reduce__": reduce,
        "items": items,
        "values": values,
    }

    if conflicts := [p for p in properties if p in methods]:
        conflicts_str = ", ".join(conflicts)
        logger.debug(
            "The following methods are unavailable on the struct "
            f"due to having the same name as a field: {conflicts_str}"
        )
        for conflict in conflicts:
            del methods[conflict]

    struct_def = make_dataclass(
        name,
        properties,
        namespace=methods,
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
        self.data_abi_types: list[EventABIType] = [i for i in abi.inputs if not i.indexed]

        names = [i.name for i in abi.inputs]
        if len(set(names)) < len(names):
            raise ValueError("duplicate names found in log input", abi)

    @property
    def event_name(self):
        return self.abi.name

    def decode(self, topics: list[str], data: str, use_hex_on_fail: bool = False) -> dict:
        decoded = {}
        for abi, topic_value in zip(self.topic_abi_types, topics[1:]):
            # reference types as indexed arguments are written as a hash
            # https://docs.soliditylang.org/en/v0.8.15/contracts.html#events
            abi_type = "bytes32" if is_dynamic_sized_type(abi.type) else abi.canonical_type
            hex_value = decode_hex(topic_value)

            try:
                value = decode([abi_type], hex_value)[0]
            except InsufficientDataBytes as err:
                warning_message = f"Failed to decode log topic '{self.event_name}'."

                # Try again with strict=False
                try:
                    value = decode([abi_type], hex_value, strict=False)[0]
                except Exception:
                    # Even with strict=False, we failed to decode.
                    # This should be a rare occasion, if it ever happens.
                    logger.warn_from_exception(err, warning_message)
                    if use_hex_on_fail:
                        if abi.name not in decoded:
                            # This allow logs to still be findable on the receipt.
                            decoded[abi.name] = hex_value

                    else:
                        raise DecodingError(str(err)) from err

                else:
                    # This happens when providers accidentally leave off trailing zeroes.
                    warning_message = (
                        f"{warning_message} "
                        "However, we are able to get a value using decode(strict=False)"
                    )
                    logger.warn_from_exception(err, warning_message)
                    decoded[abi.name] = self.decode_value(abi_type, value)

            else:
                # The data was formatted correctly and we were able to decode logs.
                result = self.decode_value(abi_type, value)
                decoded[abi.name] = result

        data_abi_types = [abi.canonical_type for abi in self.data_abi_types]
        hex_data = decode_hex(data) if isinstance(data, str) else data

        try:
            data_values = decode(data_abi_types, hex_data)
        except InsufficientDataBytes as err:
            warning_message = f"Failed to decode log data '{self.event_name}'."

            # Try again with strict=False
            try:
                data_values = decode(data_abi_types, hex_data, strict=False)
            except Exception:
                # Even with strict=False, we failed to decode.
                # This should be a rare occasion, if it ever happens.
                logger.warn_from_exception(err, warning_message)
                if use_hex_on_fail:
                    for abi in self.data_abi_types:
                        if abi.name not in decoded:
                            # This allow logs to still be findable on the receipt.
                            decoded[abi.name] = hex_data

                else:
                    raise DecodingError(str(err)) from err

            else:
                # This happens when providers accidentally leave off trailing zeroes.
                warning_message = (
                    f"{warning_message} "
                    "However, we are able to get a value using decode(strict=False)"
                )
                logger.warn_from_exception(err, warning_message)
                for abi, value in zip(self.data_abi_types, data_values):
                    decoded[abi.name] = self.decode_value(abi.canonical_type, value)

        else:
            # The data was formatted correctly and we were able to decode logs.
            for abi, value in zip(self.data_abi_types, data_values):
                decoded[abi.name] = self.decode_value(abi.canonical_type, value)

        return decoded

    def decode_value(self, abi_type: str, value: Any) -> Any:
        if abi_type == "bytes32":
            return HexBytes(value)

        elif isinstance(value, (list, tuple)) and is_array(abi_type):
            sub_type = "[".join(abi_type.split("[")[:-1])
            return [self.decode_value(sub_type, v) for v in value]

        elif isinstance(value, (list, tuple)):
            parser = StructParser(self.abi)
            result = parser.decode_input([value])
            return result[0] if len(result) == 1 else result

        # NOTE: All the rest of the types are handled by the
        #  ecosystem API through the calling function.

        return value


def _enrich_natspec(natspec: str) -> str:
    # Ensure the natspec @-words are highlighted.
    replacement = r"[bright_red]\1[/]"
    return re.sub(NATSPEC_KEY_PATTERN, replacement, natspec)
