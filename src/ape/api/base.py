from abc import ABC
from abc import abstractmethod as apimethod
from typing import List

from pydantic import BaseModel


class API(ABC, BaseModel):
    def __dir__(self) -> List[str]:
        # Filter out private members
        return [member for member in super().__dir__() if not member.startswith("_")]


__all__ = [
    "API",
    "apimethod",
]
