import sys

# We can remove this once we stop supporting python3.7.
if sys.version_info >= (3, 8):
    from functools import cached_property  # type: ignore
    from functools import singledispatchmethod  # type: ignore
    from importlib import metadata  # type: ignore
    from typing import Literal
else:
    import importlib_metadata as metadata  # type: ignore
    from backports.cached_property import cached_property  # type: ignore
    from singledispatchmethod import singledispatchmethod  # type: ignore
    from typing_extensions import Literal
