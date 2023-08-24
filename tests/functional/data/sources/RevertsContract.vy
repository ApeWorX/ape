# @version 0.3.7

import interfaces.ISubReverts as ISubReverts

sub_reverts: public(ISubReverts)
MAX_NUM: constant(uint256) = 32

@external
def __init__(sub_reverts: ISubReverts):
    self.sub_reverts = sub_reverts

@external
@nonreentrant('lock')
def revertStrings(a: uint256) -> bool:
    assert a != 0, "zero"
    assert a != 1  # dev: one
    assert a != 2, "two"  # dev: error
    assert a != 3  # error

    # Put random stuff in middle of function for testing purposes.
    i2: uint256 = 0
    for i in [1, 2, 3, 4, 5]:
        i2 = self.noop(i)
        if a != i2:
            continue

    assert a != 4  # dev: such modifiable, wow
    x: uint256 = 125348 / a
    assert x < 21 # dev: foobarbaz
    if a != 31337:
        return True
    raise "awesome show"  # dev: great job

@external
def subRevertStrings(a: uint256) -> bool:
    return self.sub_reverts.revertStrings(a)

@external
def revertStrings2(a: uint256) -> bool:
    assert a != 0, "zero"
    assert a != 1  # dev: one
    assert a != 2, "two"  # dev: error
    assert a != 3  # error
    assert a != 4  # dev: such modifiable, wow

    for i in range(MAX_NUM):
        assert i != a  # dev: loop test

    if a != 31337:
        return True
    raise "awesome show"  # dev: great job

@pure
@external
def revertStringsCall(a: uint256) -> bool:
    assert a != 0
    assert a != 1, "TEST"  # dev: one
    return True


@pure
@internal
def noop(a: uint256) -> uint256:
    return a
