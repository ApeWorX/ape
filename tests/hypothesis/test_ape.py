# This test code was written by the `hypothesis.extra.ghostwriter` module
# and is provided under the Creative Commons Zero public domain dedication.

from hypothesis import given
from hypothesis import strategies as st

import ape._cli


@given(message=st.one_of(st.none(), st.text()))
def test_fuzz_Abort(message):
    ape._cli.Abort(message=message)


@given(name=st.text())
def test_fuzz_clean_plugin_name(name):
    ape._cli.clean_plugin_name(name=name)
