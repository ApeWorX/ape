from abc import ABCMeta, abstractmethod
from functools import partial

from dataclassy import dataclass
from dataclassy.dataclass import DataClassMeta


class AbstractDataClassMeta(DataClassMeta, ABCMeta):
    pass


abstractdataclass = partial(dataclass, kwargs=True, meta=AbstractDataClassMeta)


__all__ = [
    "abstractdataclass",
    "abstractmethod",
    "AbstractDataClassMeta",
    "dataclass",
]
