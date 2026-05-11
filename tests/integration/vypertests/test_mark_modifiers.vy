# pragma version ~=0.4.3


@external
def test_xfail():
    """
    @custom:ape-mark-xfail "Should not execute"
    """
    raise "Fails for any reason"


@external
def test_parametrizing(i: uint256):
    """
    @custom:ape-mark-parametrize i
    - 1
    - 2
    - 3
    """
    assert i > 0


@external
def test_parametrizing_multiple_args(a: address, b: uint256):
    """
    @custom:ape-mark-parametrize a,b
    - (0x1, 1)
    - (0x2, 2)
    - (0x3, 3)
    """
    assert convert(a, uint256) == b
