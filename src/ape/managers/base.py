from ape.utils import ManagerAccessMixin


class BaseManager(ManagerAccessMixin):
    """
    Base manager that allows us to add other IPython integration features
    """

    def _repr_mimebundle_(self, include=None, exclude=None):
        # This works better than AttributeError for Ape.
        raise NotImplementedError("This manager does not implement '_repr_mimebundle_'.")

    def _ipython_display_(self, include=None, exclude=None):
        # This works better than AttributeError for Ape.
        raise NotImplementedError("This manager does not implement '_ipython_display_'.")
