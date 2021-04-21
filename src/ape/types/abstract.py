import json
from copy import deepcopy
from pathlib import Path
from typing import Dict

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


def remove_none_fields(data):
    if isinstance(data, dict):
        return {
            k: remove_none_fields(v)
            for k, v in data.items()
            if v is not None and remove_none_fields(v) is not None
        }

    elif isinstance(data, list):
        return [
            remove_none_fields(v)
            for v in data
            if v is not None and remove_none_fields(v) is not None
        ]

    return data


@dc.dataclass(slots=True, kwargs=True)
class SerializableType:
    def to_dict(self) -> Dict:
        return remove_none_fields({k: v for k, v in dc.asdict(self).items() if v})

    @classmethod
    def from_dict(cls, params: Dict):
        params = deepcopy(params)
        return cls(**params)  # type: ignore


class FileMixin(SerializableType):
    @classmethod
    def from_file(cls, path: Path):
        return cls.from_dict(json.load(path.open()))

    def to_file(self, path: Path):
        # NOTE: EIP-2678 specifies document *must* be tightly packed
        # NOTE: EIP-2678 specifies document *must* have sorted keys
        json.dump(self.to_dict(), path.open("w"), indent=4, sort_keys=True)
