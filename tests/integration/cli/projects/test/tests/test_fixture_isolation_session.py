def test_session(chain, session_one, session_two):
    """
    `session_one` mines 4 and `session_two` mines 2,
    so we expected 6.
    """
    assert chain.blocks.height == 6


def test_session2(chain):
    """
    Session isolation doesn't revert other session fixtures,
    so we are still at 6.
    """
    assert chain.blocks.height == 6
