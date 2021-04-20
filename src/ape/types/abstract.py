import json
from pathlib import Path
from typing import Dict

import dataclassy as dc


@dc.dataclass(slots=True, kwargs=True)
class SerializableType:
    def to_dict(self) -> Dict:
        return {k: v for k, v in dc.asdict(self).items() if v}

    @classmethod
    def from_dict(cls, params: Dict) -> "SerializableType":
        return cls(**params)  # type: ignore


class FileMixin:
    def to_dict(self) -> Dict:
        ...

    @classmethod
    def from_dict(cls, params: Dict) -> "SerializableType":
        ...

    @classmethod
    def from_file(cls, path: Path) -> "SerializableType":
        return cls.from_dict(json.load(path.open()))

    def to_file(self, path: Path):
        json.dump(self.to_dict(), path.open("w"), indent=4)
