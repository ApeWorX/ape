# @version 0.3.7

import interfaces.ISubRevertsVy as ISubRevertsVy

sub_reverts: public(ISubRevertsVy)

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
    if a != 31337:
        return True
    raise "awesome show"  # dev: great job

@pure
@external
def revertStringsCall(a: uint256) -> bool:
    assert a != 0
    assert a != 1, "TEST"  # dev: one
    return True
