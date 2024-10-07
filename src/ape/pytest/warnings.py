"""
Warnings are great for Pytest because they always show up
at the end of a test-run.
"""

import warnings


class InvalidIsolationWarning(Warning):
    """
    Occurs when fixtures disrupt isolation causing performance degradation.
    """


def warn_invalid_isolation():
    message = (
        "Invalid isolation; Ensure session|package|module|class scoped fixtures "
        "run earlier. Rebasing fixtures is costly."
    )
    warnings.warn(message, InvalidIsolationWarning)
