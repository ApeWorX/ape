# @version 0.3.7

@external
def revertStrings(a: uint256) -> bool:
    assert a != 0, "zero"
    assert a != 1  # dev: one
    assert a != 2, "two"  # dev: error
    assert a != 3  # error
    assert a != 4  # dev: such modifiable, wow
    if a != 31337:
        return True
    raise "awesome show"  # dev: great job
