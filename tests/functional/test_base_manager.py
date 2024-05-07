import pytest

from ape.exceptions import APINotImplementedError
from ape.managers.base import BaseManager


@pytest.fixture(scope="module")
def manager():
    class MyManager(BaseManager):
        pass

    return MyManager()


@pytest.mark.parametrize("fn_name", ("_repr_mimebundle_", "_ipython_display_"))
def test_ipython_integration_defaults(manager, fn_name):
    """
    Test default behavior for IPython integration methods.
    The base-manager short-circuits to NotImplementedError to avoid
    dealing with any custom `__getattr__` logic entirely. This prevents
    side-effects such as unnecessary compiling in the ProjectManager.
    """
    with pytest.raises(APINotImplementedError):
        fn = getattr(manager, fn_name)
        fn()
