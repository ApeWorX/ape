# This test code was written by the `hypothesis.extra.ghostwriter` module
# and is provided under the Creative Commons Zero public domain dedication.

from hypothesis import given
from hypothesis import strategies as st

import ape.plugins
from ape.plugins.pluggy_patch import PluginType


@given(name=st.text())
def test_fuzz_clean_plugin_name(name):
    ape.plugins.clean_plugin_name(name=name)


@given(plugin_type=st.just(PluginType))
def test_fuzz_register(plugin_type):
    ape.plugins.register(plugin_type=plugin_type)
