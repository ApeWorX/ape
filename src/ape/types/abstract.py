import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Optional, Set, Union

import dataclassy as dc


def update_params(params, param_name, param_type):
    if param_name in params and params[param_name]:
        params[param_name] = param_type.from_dict(params[param_name])


def update_list_params(params, param_name, param_type):
    if param_name in params and params[param_name]:
        params[param_name] = [param_type.from_dict(p) for p in params[param_name]]


def update_dict_params(params, param_name, param_type):
    if param_name in params and params[param_name]:
        for key in params[param_name]:
            params[param_name][key] = param_type.from_dict(params[param_name][key])


def remove_empty_fields(data, keep_fields: Optional[Set[str]] = None):
    if isinstance(data, dict):
        return {
            k: v
            for k, v in zip(data.keys(), map(remove_empty_fields, data.values()))
            if isinstance(v, bool) or (keep_fields and k in keep_fields) or v
        }

    elif isinstance(data, list):
        return [v for v in map(remove_empty_fields, data) if isinstance(v, bool) or v]

    return data


def to_dict(v: Any) -> Optional[Union[list, dict, str, int, bool]]:
    if isinstance(v, SerializableType):
        return v.to_dict()

    elif isinstance(v, list):
        return [to_dict(i) for i in v]  # type: ignore

    elif isinstance(v, dict):
        return {k: to_dict(i) for k, i in v.items()}

    elif isinstance(v, (str, int, bool)) or v is None:
        return v

    else:
        raise Exception(f"Unhandled type '{type(v)}'")


@dc.dataclass(slots=True, kwargs=True, repr=True)
class SerializableType:
    _keep_fields_: Set[str] = set()
    _skip_fields_: Set[str] = set()

    def to_dict(self) -> Dict:
        data = {
            k: to_dict(v)
            for k, v in dc.values(self).items()
            if not (k.startswith("_") or k in self._skip_fields_)
        }
        return remove_empty_fields(data, keep_fields=self._keep_fields_)

    @classmethod
    def from_dict(cls, params: Dict):
        params = deepcopy(params)
        return cls(**params)  # type: ignore


class FileMixin(SerializableType):
    @classmethod
    def from_file(cls, path: Path):
        with path.open("r") as f:
            return cls.from_dict(json.load(f))

    def to_file(self, path: Path):
        # NOTE: EIP-2678 specifies document *must* be tightly packed
        # NOTE: EIP-2678 specifies document *must* have sorted keys
        with path.open("w") as f:
            json.dump(self.to_dict(), f, indent=4, sort_keys=True)
