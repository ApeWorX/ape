# This test code was written by the `hypothesis.extra.ghostwriter` module
# and is provided under the Creative Commons Zero public domain dedication.

from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

import ape.managers


@given(data_folder=st.builds(Path))
def test_fuzz_DependencyManager(data_folder):
    ape.managers.DependencyManager(data_folder=data_folder)


@given(path=st.builds(Path))
def test_fuzz_ProjectManager(path):
    ape.managers.ProjectManager(path=path)
