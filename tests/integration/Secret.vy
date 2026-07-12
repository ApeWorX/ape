secret: uint256


@deploy
def __init__():
    # NOTE: "Impossible" for fuzzing to randomly guess this without a lot of passes.
    #       If it does, simply delete the `.hypothesis` folder.
    self.secret = 703895692105206524502680346056234


@external
def add(a: uint256):
    self.secret += a
    assert self.secret != 2378945823475283674509246524589


@external
def sub(a: uint256, b: uint256):
    self.secret -= a % b
    assert self.secret != 2378945823475283674509246524589
