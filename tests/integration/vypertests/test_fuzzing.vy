from ethereum.ercs import IERC20

@external
def test_with_fuzzing(a: uint256):
    """
    @custom:ape-fuzzer-max-examples 200
    @custom:ape-fuzzer-deadline 500
    """
    assert a != 29678634502528050652056023465820843, "Found a rare bug!"


@external
def test_token_approvals(token: IERC20, other: address, amount: uint256):
    """
    @custom:ape-fuzzer-deadline 1000
    @custom:ape-check-emits
    - token.Approval(owner=msg.sender, spender=other, value=amount)
    """
    assert extcall token.approve(other, amount)
    assert staticcall token.allowance(msg.sender, other) == amount
