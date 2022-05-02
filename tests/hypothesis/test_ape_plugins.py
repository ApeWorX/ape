# This test code was written by the `hypothesis.extra.ghostwriter` module
# and is provided under the Creative Commons Zero public domain dedication.

from hypothesis import given
from hypothesis import strategies as st

import ape_plugins._cli
from ape.logging import CliLogger
from ape_plugins._cli import ApePlugin


@given(name=st.text())
def test_fuzz_ApePlugin(name):
    ape_plugins._cli.ApePlugin(name=name)


@given(logger=st.builds(CliLogger), plugin=st.builds(ApePlugin))
def test_fuzz_ModifyPluginResultHandler(logger, plugin):
    ape_plugins._cli.ModifyPluginResultHandler(logger=logger, plugin=plugin)


@given(help=st.text())
def test_fuzz_upgrade_option(help):
    ape_plugins._cli.upgrade_option(help=help)
