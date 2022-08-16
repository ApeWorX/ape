import pytest
from hypothesis import given, strategies

from ape.utils import parse_type

# An alphanumeric type identifier or array declaration.
IDENT = r"(\w+(\[\])?)"

# A tuple declaration with one or more items.
# e.g. (int,) or (int, int) or (int, int,) etc.
TUPLE = rf"(\({IDENT},(\s*{IDENT},?)*\))"

# Adding optional nesting to the tuple pattern.
# e.g. (int,) or (int, int) or ((int,), int) etc.
TUPLE = rf"(\(({IDENT}|{TUPLE}),(\s*({IDENT}|{TUPLE}),?)*\))"

# The full type declaration pattern which matches:
# - type identifier
# - array declaration
# - tuples of type/array
# - tuples of type/array or tuples
TYPE_DECL = rf"^({IDENT}|{TUPLE})$"


@pytest.mark.fuzzing
@given(strategies.from_regex(TYPE_DECL))
def test_parse_type(s):
    # Examples matching strings from above regex:
    #   - int
    #   - int[]
    #   - uint256
    #   - (int,)
    #   - (int[],)
    #   - (int, int,)
    #   - (int, int)
    #   - (int, int, int)
    #   - (int, int, int,)
    #   - ((int, int), int)
    #   - ((int, int[],), int)
    #
    # Some examples of non-matching strings:
    #   - [int,]
    #   - (int ) [] asdf ff 33 asdf
    #   - ,int
    #   - int,
    # See tests in `tests_contracts` for specific ABI parsing tests.

    assert parse_type(s)
