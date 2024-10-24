from collections.abc import Callable, Iterator, Sequence
from importlib import import_module
from typing import Annotated, TypeVar, Union, overload

from pydantic import BeforeValidator


def _hex_int_validator(value, info):
    access = import_module("ape.utils.basemodel").ManagerAccessMixin
    convert = access.conversion_manager.convert
    return convert(value, int)


HexInt = Annotated[int, BeforeValidator(_hex_int_validator)]
"""
Validate any hex-str or bytes into an integer.
To be used on pydantic-fields.
"""

_T = TypeVar("_T")  # _LazySequence generic.


class _LazySequence(Sequence[_T]):
    def __init__(self, generator: Union[Iterator[_T], Callable[[], Iterator[_T]]]):
        self._generator = generator
        self.cache: list = []

    @overload
    def __getitem__(self, index: int) -> _T: ...

    @overload
    def __getitem__(self, index: slice) -> Sequence[_T]: ...

    def __getitem__(self, index: Union[int, slice]) -> Union[_T, Sequence[_T]]:
        if isinstance(index, int):
            while len(self.cache) <= index:
                # Catch up the cache.
                if value := next(self.generator, None):
                    self.cache.append(value)

            return self.cache[index]

        elif isinstance(index, slice):
            # TODO: Make slices lazier. Right now, it deqeues all.
            for item in self.generator:
                self.cache.append(item)

            return self.cache[index]

        else:
            raise TypeError("Index must be int or slice.")

    def __len__(self) -> int:
        # NOTE: This will deque everything.

        for value in self.generator:
            self.cache.append(value)

        return len(self.cache)

    def __iter__(self) -> Iterator[_T]:
        yield from self.cache
        for value in self.generator:
            yield value
            self.cache.append(value)

    @property
    def generator(self) -> Iterator:
        if callable(self._generator):
            self._generator = self._generator()

        assert isinstance(self._generator, Iterator)  # For type-checking.
        yield from self._generator
