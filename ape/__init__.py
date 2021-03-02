from importlib.metadata import version, PackageNotFoundError

# NOTE: Do this before anything else
from . import _setup  # noqa E302

try:
    __version__ = version(__name__)
except PackageNotFoundError:
    # package is not installed
    __version__ = "<unknown>"
