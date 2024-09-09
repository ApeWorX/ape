import doctest

extensions = ["sphinx_ape"]

# -- Doctest configuration --

doctest_default_flags = (
    0
    | doctest.DONT_ACCEPT_TRUE_FOR_1
    | doctest.ELLIPSIS
    | doctest.IGNORE_EXCEPTION_DETAIL
    | doctest.NORMALIZE_WHITESPACE
)

doctest_global_setup = """
from ape import *
"""
