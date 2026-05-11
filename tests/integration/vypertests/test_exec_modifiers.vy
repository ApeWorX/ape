# pragma version ~=0.4.3
from ethereum.ercs import IERC20


@external
def test_default_executor(deployer: address, token: IERC20, other: address):
    assert deployer == msg.sender

    assert staticcall token.balanceOf(deployer) == 1000
    assert staticcall token.balanceOf(other) == 0

    extcall token.transfer(other, 1000)

    assert staticcall token.balanceOf(deployer) == 0
    assert staticcall token.balanceOf(other) == 1000


@external
def test_prank_executor(deployer: address, token: IERC20, other: address):
    """
    @custom:ape-test-after test_default_executor
    @custom:ape-test-executor other
    """

    assert other == msg.sender

    assert staticcall token.balanceOf(deployer) == 0
    assert staticcall token.balanceOf(other) == 1000

    extcall token.approve(deployer, 1000)

    assert staticcall token.balanceOf(deployer) == 0
    assert staticcall token.balanceOf(other) == 1000


@external
def test_default_executor_again(deployer: address, token: IERC20, other: address):
    """@custom:ape-test-after test_prank_executor"""

    assert deployer == msg.sender

    assert staticcall token.balanceOf(deployer) == 0
    assert staticcall token.balanceOf(other) == 1000

    extcall token.transferFrom(other, deployer, 1000)

    assert staticcall token.balanceOf(deployer) == 1000
    assert staticcall token.balanceOf(other) == 0
