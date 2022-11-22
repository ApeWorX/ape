from typing import Any, Dict, List, Tuple, Union
from ape.utils import is_array

def parse_type(type: Dict[str, Any]) -> Union[str, Tuple, List]:
    """
    Parses ``ABIType.dict()`` into Python types.
    Deprecated: Use :class:`~ape.api.networks.EcosystemAPI` implemented methods.
    """
    if "tuple" in type["type"]:
        r = tuple([parse_type(c) for c in type["components"]])
        if is_array(type["type"]):
            return [r]
        return r
    else:
        return type["type"]
