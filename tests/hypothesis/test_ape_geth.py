# This test code was written by the `hypothesis.extra.ghostwriter` module
# and is provided under the Creative Commons Zero public domain dedication.

from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from ape.api.networks import NetworkAPI
from ape_geth.providers import GethProvider


@given(
    name=st.text(),
    network=st.builds(NetworkAPI),
    provider_settings=st.builds(dict),
    data_folder=st.builds(Path),
    request_header=st.builds(dict),
    cached_chain_id=st.one_of(st.none(), st.integers()),
)
def test_fuzz_GethProvider(
    name, network, provider_settings, data_folder, request_header, cached_chain_id
):
    GethProvider(
        name=name,
        network=network,
        provider_settings=provider_settings,
        data_folder=data_folder,
        request_header=request_header,
        cached_chain_id=cached_chain_id,
    )
