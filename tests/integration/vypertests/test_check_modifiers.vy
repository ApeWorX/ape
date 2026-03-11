# pragma version ~=0.4.3
from ethereum.ercs import IERC20

@external
def test_it_raises():
    """ @custom:ape-check-reverts It works!"""
    assert False, "It works!"


@external
def test_emits(token: IERC20, other: address):
    """
    @custom:ape-check-emits
    - token.Approval(owner=msg.sender, spender=other, value=100_000)
    - token.Approval(spender=other, value=10_000)
    - token.Approval(owner=msg.sender, spender=other)
    - token.Approval(owner=msg.sender, value=100)
    - token.Approval(value=10)
    - token.Approval()
    """
    extcall token.approve(other, 100_000)
    extcall token.approve(other, 10_000)
    extcall token.approve(other, 1_000)
    extcall token.approve(other, 100)
    extcall token.approve(other, 10)
    extcall token.approve(other, 1)
