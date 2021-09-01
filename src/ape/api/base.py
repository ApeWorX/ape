from abc import ABC
from abc import abstractmethod as apimethod
from typing import List

from pydantic import BaseModel

from ape.utils import cached_property


class API(ABC, BaseModel):
    class Config:
        keep_untouched = (cached_property,)  #

    # NOTE: Due to https://github.com/samuelcolvin/pydantic/issues/1241
    #       we have to add this cached property workaround in order to avoid this error:
    #
    #           TypeError: cannot pickle '_thread.RLock' object

    def __dir__(self) -> List[str]:
        # Filter out private members
        return [member for member in super().__dir__() if not member.startswith("_")]


__all__ = [
    "API",
    "apimethod",
]
