import pytest
from hypothesis import given, strategies

from ape.utils import parse_type


@pytest.mark.fuzzing
@given(strategies.from_regex(r"\(*[\w|, []]*\)*"))
def test_parse_type(s):
    # Example matching strings from above regex:
    #   * (int, int)
    #   * ((int, int), int)
    #   * int
    #   * uint256
    #   * int[]
    #   * (asd ) [] asdf ff 33 asdf
    #
    # See tests in `tests_contracts` for specific ABI parsing tests.

    assert parse_type(s)
