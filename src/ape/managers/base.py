from ape.utils.basemodel import ManagerAccessMixin
from ape.utils.misc import raises_not_implemented


class BaseManager(ManagerAccessMixin):
    """
    Base manager that allows us to add other IPython integration features
    """

    @raises_not_implemented
    def _repr_mimebundle_(self, include=None, exclude=None):
        # This works better than AttributeError for Ape.
        pass

    @raises_not_implemented
    def _ipython_display_(self, include=None, exclude=None):
        # This works better than AttributeError for Ape.
        pass
