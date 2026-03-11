# NOTE: Fixtures for use with both Solidity and Vyper "Contract Tests" feature
from pathlib import Path
import pytest

from hypothesis import strategies as st
from eth_abi.tools import get_abi_strategy

from ape.utils import ZERO_ADDRESS


@pytest.fixture(scope="session")
def openzeppelin(project):
    dep = project.dependencies["openzeppelin"]
    return dep[max(dep)]


@pytest.fixture(scope="session")
def deployer(accounts):
    # NOTE: Same as who deployed test
    return accounts[-1]


@pytest.fixture(scope="session")
def token(openzeppelin, deployer):
    token = openzeppelin.ERC20Mock.deploy(sender=deployer)
    token.mint(deployer, 1000, sender=deployer)
    return token


@pytest.fixture(scope="session")
def other(accounts):
    return accounts[1]


@pytest.fixture(scope="session")
def account(token):
    return (
        get_abi_strategy("address")
        # We do not want the zero address, it fails OZ's ERC20 code
        # Also skip token address, it doesn't make sense
        .filter(lambda a: a not in (ZERO_ADDRESS, token.address))
    )


@pytest.fixture(scope="session")
def amount():
    return st.integers(min_value=1, max_value=100 * 10**18)


@pytest.fixture(scope="session")
def bips():
    # NOTE: Emulates a "basis point" type, excluding 0%
    return st.integers(min_value=1, max_value=10_000)


@pytest.fixture(scope="session")
def secret(compilers, accounts):
    ct = compilers.get_compiler("vyper").compile_code(
        (Path(__file__).parent / "Secret.vy").read_text()
    )
    return accounts[-1].deploy(ct)
