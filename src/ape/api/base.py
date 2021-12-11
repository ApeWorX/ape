from abc import ABCMeta
from abc import abstractmethod as _abstractmethod
from functools import partial
from typing import Callable

from dataclassy import dataclass as _dataclass
from dataclassy.dataclass import DataClassMeta


class AbstractDataClassMeta(DataClassMeta, ABCMeta):
    pass


abstractmethod: Callable = _abstractmethod
"""
An API method.
"""

dataclass = _dataclass
"""
A class of serializable properties, like a struct.
"""

abstractdataclass = partial(dataclass, kwargs=True, meta=AbstractDataClassMeta)
"""
An API version of a :meth:`~ape.api.base.dataclass`.
"""


__all__ = [
    "abstractdataclass",
    "abstractmethod",
    "AbstractDataClassMeta",
    "dataclass",
]
