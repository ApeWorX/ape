@external
def num_add(i: int128) -> int128:
    return (2**127-1) + i


@external
def neg_num_add(i: int128) -> int128:
    return i - (2**127-1)


@external
def div_zero(i: int128) -> int128:
    return 4 / i


@external
def mod_zero(i: int128) -> int128:
    return 4 % i
