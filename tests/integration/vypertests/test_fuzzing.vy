from ethereum.ercs import IERC20

@external
def test_with_fuzzing(a: uint256):
    """@custom:ape-fuzzer-max-examples 200"""
    assert a != 29678634502528050652056023465820843, "Found a rare bug!"


@external
def test_token_approvals(token: IERC20, amount: uint256):
    """@custom:ape-fuzzer-deadline 1000"""
    assert extcall token.approve(msg.sender, amount)
    assert staticcall token.allowance(self, msg.sender) == amount
