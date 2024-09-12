"""
'test_fixture_isolation.py' runs before this module.
We are testing that we go back to an expected session-level
state without any of the module-level state from
'test_fixture_isolation.py'.
"""


def test_session(chain):
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
