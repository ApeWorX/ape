import inspect
from abc import ABC
from collections.abc import Callable, Iterator, Sequence
from importlib import import_module
from pathlib import Path
from sys import getrecursionlimit
from typing import TYPE_CHECKING, Any, ClassVar, Optional, Union

from ethpm_types import BaseModel as EthpmTypesBaseModel
from pydantic import BaseModel as RootBaseModel
from pydantic import ConfigDict

from ape.exceptions import ApeAttributeError, ApeIndexError, ProviderNotConnectedError
from ape.logging import logger
from ape.utils.misc import log_instead_of_fail, raises_not_implemented
from ape.utils.rpc import USER_AGENT

if TYPE_CHECKING:
    from pydantic.main import Model

    from ape.api.providers import ProviderAPI
    from ape.managers.accounts import AccountManager
    from ape.managers.chain import ChainManager
    from ape.managers.compilers import CompilerManager
    from ape.managers.config import ConfigManager
    from ape.managers.converters import ConversionManager
    from ape.managers.networks import NetworkManager
    from ape.managers.plugins import PluginManager
    from ape.managers.project import DependencyManager, ProjectManager
    from ape.managers.query import QueryManager
    from ape.pytest.runners import PytestApeRunner


class classproperty(object):
    def __init__(self, fn: Callable):
        self.fn = fn

    def __get__(self, obj, owner) -> Any:
        return self.fn(owner)


class manager_access(property):
    _cache = None

    def __init__(self, fn):
        self.fn = fn

    def __get__(self, obj, owner) -> Any:  # type: ignore[override]
        if self._cache is None:
            self._cache = self.fn(owner)

        return self._cache


class _RecursionChecker:
    # A helper for preventing the recursion errors
    # that happen in custom __getattr__ methods.

    def __init__(self):
        self.THRESHOLD: int = getrecursionlimit()
        self.getattr_checking: dict[str, int] = {}
        self.getattr_errors: dict[str, Exception] = {}

    @log_instead_of_fail(default="<_RecursionChecker>")
    def __repr__(self) -> str:
        return repr(self.getattr_checking)

    def check(self, name: str) -> bool:
        return (self.getattr_checking.get(name, 0) or 0) >= self.THRESHOLD

    def add(self, name: str):
        if name in self.getattr_checking:
            self.getattr_checking[name] += 1
        else:
            self.getattr_checking[name] = 1

    def reset(self, name: str):
        self.getattr_checking.pop(name, None)
        self.getattr_errors.pop(name, None)


_recursion_checker = _RecursionChecker()


# TODO: Delete in 0.9 (deprecated & no longer used anywhere)
class injected_before_use(property):
    """
    Injected properties are injected class variables that must be set before use.

    **NOTE**: do not appear in a Pydantic model's set of properties.
    """

    def __get__(self, *args):
        arg_strs = []
        for argument in args:
            try:
                arg_str = str(argument)
            except Exception as err:
                logger.debug(f"Failed calling __str__. Exception: {err}")
                arg_strs.append("<?>")
                continue

            arg_strs.append(arg_str)

        error_message = "Value not set"
        if arg_strs:
            error_message = f"{error_message} (arguments={', '.join(arg_strs)})"

        error_message = f"{error_message}. Please inject this property before calling."
        raise ValueError(error_message)


def only_raise_attribute_error(fn: Callable) -> Any:
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except AttributeError:
            raise  # Don't modify or log attr errors.
        except Exception as err:
            # Wrap the exception in AttributeError
            logger.log_debug_stack_trace()
            raise ApeAttributeError(f"{err}") from err

    return wrapper


class ManagerAccessMixin:
    """
    A mixin for accessing Ape's manager at the class level.

    Usage example:

        from ape.utils import ManagerAccessMixin

        class MyClass(ManagerAccessMixin):
            def my_function(self):
                accounts = self.account_manager  # And so on!
    """

    _test_runner: ClassVar[Optional["PytestApeRunner"]] = None

    @manager_access
    def account_manager(cls) -> "AccountManager":
        """
        The :class:`~ape.managers.accounts.AccountManager`.
        """
        accounts = import_module("ape.managers.accounts")
        return accounts.AccountManager()

    @manager_access
    def chain_manager(cls) -> "ChainManager":
        """
        The :class:`~ape.managers.chain.ChainManager`.
        """
        chain = import_module("ape.managers.chain")
        return chain.ChainManager()

    @manager_access
    def compiler_manager(cls) -> "CompilerManager":
        """
        The :class:`~ape.managers.compilers.CompilerManager`.
        """
        compilers = import_module("ape.managers.compilers")
        return compilers.CompilerManager()

    @manager_access
    def config_manager(cls) -> "ConfigManager":
        """
        The :class:`~ape.managers.config.ConfigManager`.
        """
        config = import_module("ape.managers.config")
        return config.ConfigManager(
            request_header={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
        )

    @manager_access
    def conversion_manager(cls) -> "ConversionManager":
        """
        The :class:`~ape.managers.converters.ConversionManager`.
        """
        converters = import_module("ape.managers.converters")
        return converters.ConversionManager()

    @manager_access
    def local_project(cls) -> "ProjectManager":
        """
        A :class:`~ape.managers.project.ProjectManager` pointed
        at the current-working directory.
        """
        project = import_module("ape.managers.project")
        return project.ProjectManager(Path.cwd())

    @manager_access
    def network_manager(cls) -> "NetworkManager":
        """
        The :class:`~ape.managers.networks.NetworkManager`.
        """
        networks = import_module("ape.managers.networks")
        return networks.NetworkManager()

    @manager_access
    def plugin_manager(cls) -> "PluginManager":
        """
        The :class:`~ape.managers.plugins.PluginManager`.
        """
        plugins = import_module("ape.managers.plugins")
        return plugins.PluginManager()

    @classproperty
    def Project(cls) -> type["ProjectManager"]:
        """
        The ``Project`` factory class for creating
        other local-projects.
        """
        project = import_module("ape.managers.project")
        return project.ProjectManager

    @manager_access
    def query_manager(cls) -> "QueryManager":
        """
        The :class:`~ape.managers.query.QueryManager`.
        """
        query = import_module("ape.managers.query")
        return query.QueryManager()

    @classproperty
    def provider(cls) -> "ProviderAPI":
        """
        The current active provider if connected to one.

        Raises:
            :class:`~ape.exceptions.ProviderNotConnectedError`: When there is
            no active provider at runtime.

        Returns:
            :class:`~ape.api.providers.ProviderAPI`
        """
        if provider := cls.network_manager.active_provider:
            return provider

        raise ProviderNotConnectedError()

    @classproperty
    def dependency_manager(cls) -> "DependencyManager":
        # We make this available for more intuitive access to
        # global dependencies, which any project has access to.
        return cls.local_project.dependencies


class BaseInterface(ManagerAccessMixin, ABC):
    """
    Abstract class that has manager access.
    """


def _get_alt(name: str) -> Optional[str]:
    alt = None
    if ("-" not in name and "_" not in name) or ("-" in name and "_" in name):
        alt = None
    elif "-" in name:
        alt = name.replace("-", "_")
    elif "_" in name:
        alt = name.replace("_", "-")

    return alt


class _AttrLookup(dict):
    """
    Used when given extra attributes via a callback
    that takes the attribute name.
    """

    def __init__(
        self,
        callback: Callable[
            [
                str,
            ],
            None,
        ],
    ):
        self._callback = callback

    def __contains__(self, item) -> bool:
        return self._callback(item) is not None

    @only_raise_attribute_error
    def __getattr__(self, item):
        res = self._callback(item)
        if res is None:
            # attr-lookups cannot return None!
            raise AttributeError(item)

        return res

    def __getitem__(self, item):
        return self._callback(item)

    def get(self, item):  # type: ignore[override]
        return self._callback(item)


class ExtraModelAttributes(EthpmTypesBaseModel):
    """
    A class for defining extra model attributes.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    """
    The name of the attributes. This is important
    in instances such as when an attribute is missing,
    we can show a more accurate exception message.
    """

    attributes: Union[Any, Callable[[], Any], Callable[[str], Any]]
    """The attributes. The following types are supported:

    1. A model or dictionary to lookup attributes.
    2. A callable with no arguments, for lazily evaluating a model or dictionary
       for lookup.
    3. A callable with a single argument that is the attribute name. This style
       of lookup cannot be used for optionals.
    """

    include_getattr: bool = True
    """Whether to use these in ``__getattr__``."""

    include_getitem: bool = False
    """Whether to use these in ``__getitem__``."""

    additional_error_message: Optional[str] = None
    """
    An additional error message to include at the end of
    the normal IndexError message.
    """

    def __repr__(self) -> str:
        try:
            return f"<ExtraAttributes '{self.name}'>"
        except Exception:
            # Disallow exceptions in __repr__
            return "<ExtraModelAttributes>"

    def __contains__(self, name: Any) -> bool:
        attrs = self._attrs()
        try:
            name = str(name)
        except Exception:
            return False

        if name in attrs or hasattr(attrs, name):
            return True

        elif alt := _get_alt(name):
            return alt in attrs

        return False

    def get(self, name: str) -> Optional[Any]:
        """
        Get an attribute.

        Args:
            name (str): The name of the attribute.

        Returns:
            Optional[Any]: The attribute if it exists, else ``None``.
        """

        res = self._get(name)
        if res is not None:
            return res

        if alt := _get_alt(name):
            res = self._get(alt)
            if res is not None:
                return res

        return None

    def _get(self, name: str) -> Optional[Any]:
        attrs = self._attrs()
        return attrs.get(name) if hasattr(attrs, "get") else getattr(attrs, name, None)

    def _attrs(self) -> Any:
        if not isinstance(self.attributes, Callable):  # type: ignore
            # Dict or model that can do a lookup.
            return self.attributes

        signature = inspect.signature(self.attributes)
        if len(signature.parameters) == 0:
            # Lazy-eval dict.
            return self.attributes()  # type: ignore

        # Callable lookup via name.
        return _AttrLookup(self.attributes)  # type: ignore


class BaseModel(EthpmTypesBaseModel):
    """
    An ape-pydantic BaseModel.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def model_copy(
        self: "Model",
        *,
        update: Optional[dict[str, Any]] = None,
        deep: bool = False,
        cache_clear: Optional[Sequence[str]] = None,
    ) -> "Model":
        result = super().model_copy(update=update, deep=deep)

        # Clear @cached_properties
        for cached_item in cache_clear or []:
            if cached_item in result.__dict__:
                del result.__dict__[cached_item]

        return result

    @raises_not_implemented
    def _repr_mimebundle_(self, include=None, exclude=None):
        # This works better than AttributeError for Ape.
        pass

    @raises_not_implemented
    def _ipython_display_(self, include=None, exclude=None):
        # This works better than AttributeError for Ape.
        pass


def _assert_not_ipython_check(key):
    # Perf: IPython expects AttributeError here.
    if isinstance(key, str) and key == "_ipython_canary_method_should_not_exist_":
        raise AttributeError()


class ExtraAttributesMixin:
    """
    A mixin to use on models that provide ``ExtraModelAttributes``.
    **NOTE**: Must come _before_ your base-model class in subclass tuple to function.
    """

    def __ape_extra_attributes__(self) -> Iterator[ExtraModelAttributes]:
        """
        Override this method to supply extra attributes
        to a model in Ape; this allow more properties
        to be available when invoking ``__getattr__``.

        Returns:
            Iterator[:class:`~ape.utils.basemodel.ExtraModelAttributes`]: A
            series of instances defining extra model attributes.
        """
        return iter(())

    @only_raise_attribute_error
    def __getattr__(self, name: str) -> Any:
        """
        An overridden ``__getattr__`` implementation that takes into
        account :meth:`~ape.utils.basemodel.ExtraAttributesMixin.__ape_extra_attributes__`.
        """
        _assert_not_ipython_check(name)
        private_attrs = (self.__pydantic_private__ or {}) if isinstance(self, RootBaseModel) else {}
        if name in private_attrs:
            _recursion_checker.reset(name)
            return private_attrs[name]

        return get_attribute_with_extras(self, name)

    def __getitem__(self, name: Any) -> Any:
        # For __getitem__, we first try the extra (unlike `__getattr__`).
        return get_item_with_extras(self, name)


def get_attribute_with_extras(obj: Any, name: str) -> Any:
    _assert_not_ipython_check(name)
    if _recursion_checker.check(name):
        # Prevent segfaults.
        # First, attempt to get real error.
        message = f"Failed trying to get {name}"
        if real_error := _recursion_checker.getattr_errors.get(name):
            message = f"{message}. {real_error}"

        _recursion_checker.reset(name)
        raise AttributeError(message)

    _recursion_checker.add(name)

    res = None

    if not isinstance(obj, ExtraAttributesMixin):
        name = getattr(type(obj), "__name__", "obj")
        raise AttributeError(f"{name} must use the '{ExtraAttributesMixin.__name__}' mixin'")

    try:
        res = super(ExtraAttributesMixin, obj).__getattribute__(name)
    except AttributeError as base_attr_err:
        _recursion_checker.getattr_errors[name] = base_attr_err

    if res is not None:
        _recursion_checker.reset(name)
        return res

    if name.startswith("__") and name.endswith("__"):
        # Don't seek double-dunderized definitions from extras.
        raise AttributeError(name)

    # NOTE: Do not check extras within the error handler to avoid
    #   errors occurring within an exception handler (Python shows that differently).
    extras_checked = set()
    for ape_extra in obj.__ape_extra_attributes__():
        if not ape_extra.include_getattr:
            continue

        extras_checked.add(ape_extra.name)
        try:
            if name in ape_extra:
                # Attribute was found in one of the supplied
                # extra attributes mappings.
                result = ape_extra.get(name)
                # NOTE: Don't reset until _after_ we have the result.
                _recursion_checker.reset(name)
                return result

        except Exception as err:
            _recursion_checker.reset(name)
            raise ApeAttributeError(f"{name} - {err}") from err

    # The error message mentions the alternative mappings,
    # such as a contract-type map.
    base_err = None
    if name in _recursion_checker.getattr_errors:
        # There was an error getting the value. Show that.
        base_err = _recursion_checker.getattr_errors[name]
        message = str(base_err)
    else:
        message = f"'{repr(obj)}' has no attribute '{name}'"

    if extras_checked:
        extras_str = ", ".join(sorted(extras_checked))
        suffix = f"Also checked extra(s) '{extras_str}'"
        if suffix not in message:
            if message and message[-1] not in (".", "?", "!"):
                message = f"{message}."
            message = f"{message} {suffix}"

    _recursion_checker.reset(name)
    if message and message[-1] not in (".", "?", "!"):
        message = f"{message}."

    attr_err = ApeAttributeError(message)
    if base_err:
        raise attr_err from base_err
    else:
        raise attr_err


def get_item_with_extras(obj: Any, name: str) -> Any:
    # For __getitem__, we first try the extra (unlike `__getattr__`).
    extras_checked = set()
    additional_error_messages = {}
    for extra in obj.__ape_extra_attributes__():
        if not extra.include_getitem:
            continue

        if name in extra:
            return extra.get(name)

        extras_checked.add(extra.name)

        if extra.additional_error_message:
            additional_error_messages[extra.name] = extra.additional_error_message

    # NOTE: If extras were supplied, the user was expecting it to be
    #   there (unlike __getattr__).
    if extras_checked:
        prefix = f"Unable to find '{name}' in"
        if not additional_error_messages:
            extras_str = ", ".join(extras_checked)
            message = f"{prefix} any of '{extras_str}'."

        else:
            # The class is including additional error messages for the IndexError.
            message = ""
            for extra_checked in extras_checked:
                additional_message = additional_error_messages.get(extra_checked)
                suffix = f" {additional_message}" if additional_message else ""
                sub_message = f"{prefix} '{extra_checked}'.{suffix}"
                message = f"{message}\n{sub_message}" if message else sub_message

        raise ApeIndexError(message)

    # The user did not supply any extra __getitem__ attributes.
    # Do what you would have normally done.
    return super(ExtraAttributesMixin, obj).__getitem__(name)  # type: ignore


class BaseInterfaceModel(BaseInterface, BaseModel):
    """
    An abstract base-class with manager access on a pydantic base model.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def __dir__(self) -> list[str]:
        """
        **NOTE**: Should integrate options in IPython tab-completion.
        https://ipython.readthedocs.io/en/stable/config/integrating.html
        """
        # Filter out protected/private members
        return [member for member in super().__dir__() if not member.startswith("_")]
