# pragma version ~=0.4.3
from ethereum.ercs import IERC20

@external
def test_it_raises():
    """ @custom:ape-check-reverts "It works!" """
    assert False, "It works!"


@external
def test_emits(token: IERC20, executor: address):
    """
    @custom:ape-check-emits
    - token.Approval(owner=self, spender=executor, value=100_000)
    - token.Approval(spender=executor, value=10_000)
    - token.Approval(owner=self, spender=executor)
    - token.Approval(owner=self, value=100)
    - token.Approval(value=10)
    - token.Approval()
    """
    extcall token.approve(executor, 100_000)
    extcall token.approve(executor, 10_000)
    extcall token.approve(executor, 1_000)
    extcall token.approve(executor, 100)
    extcall token.approve(executor, 10)
    extcall token.approve(executor, 1)
