# pragma version ~=0.4.3

store: uint256


@external
def setUp():
    self.store += 1


@external
def test_setup_works():
    assert self.store == 1


@external
def test_setup_works_2nd_time():
    assert self.store == 1
