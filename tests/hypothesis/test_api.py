# This test code was written by the `hypothesis.extra.ghostwriter` module
# and is provided under the Creative Commons Zero public domain dedication.

from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

import ape.api
from ape_ethereum.ecosystem import Ethereum


@given(address=st.text())
def test_fuzz_Address(address):
    ape.api.Address(address=address)


@given(
    difficulty=st.one_of(st.none(), st.integers()),
    totalDifficulty=st.one_of(st.none(), st.integers()),
)
def test_fuzz_BlockConsensusAPI(difficulty, totalDifficulty):
    ape.api.BlockConsensusAPI(difficulty=difficulty, totalDifficulty=totalDifficulty)


@given(
    gasLimit=st.integers(),
    gasUsed=st.integers(),
    baseFeePerGas=st.one_of(st.none(), st.integers()),
)
def test_fuzz_BlockGasAPI(gasLimit, gasUsed, baseFeePerGas):
    ape.api.BlockGasAPI(gasLimit=gasLimit, gasUsed=gasUsed, baseFeePerGas=baseFeePerGas)


@given(__root__=st.builds(dict))
def test_fuzz_ConfigDict(__root__):
    ape.api.ConfigDict(__root__=__root__)


@given(raw_address=st.text())
def test_fuzz_ImpersonatedAccount(raw_address):
    ape.api.ImpersonatedAccount(raw_address=raw_address)


@given(
    name=st.text(),
    ecosystem=st.one_of(st.nothing(), st.builds(Ethereum)),
    data_folder=st.builds(Path),
    request_header=st.builds(dict),
)
def test_fuzz_NetworkAPI(name, ecosystem, data_folder, request_header):
    ape.api.NetworkAPI(
        name=name,
        ecosystem=ecosystem,
        data_folder=data_folder,
        request_header=request_header,
    )


@given(chain_id=st.integers(), network_id=st.integers())
def test_fuzz_create_network_type(chain_id, network_id):
    ape.api.create_network_type(chain_id=chain_id, network_id=network_id)
