import sys

# We can remove this once we stop supporting python3.7.
if sys.version_info >= (3, 8):
    from typing import Literal
else:
    from typing_extensions import Literal  # noqa F401
