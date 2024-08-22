import pytest

from ape.exceptions import ProviderNotConnectedError
from ape.logging import logger
from ape.managers.project import DependencyManager
from ape.utils.basemodel import ManagerAccessMixin, only_raise_attribute_error


class CustomClass(ManagerAccessMixin):
    pass


@pytest.mark.parametrize("accessor", (CustomClass, CustomClass()))
def test_provider(accessor, eth_tester_provider):
    assert accessor.provider == eth_tester_provider


@pytest.mark.parametrize("accessor", (CustomClass, CustomClass()))
def test_provider_not_active(networks, accessor):
    initial = networks.active_provider
    networks.active_provider = None
    try:
        with pytest.raises(ProviderNotConnectedError):
            _ = accessor.provider
    finally:
        networks.active_provider = initial


def test_only_raise_attribute_error(mocker, ape_caplog):
    spy = mocker.spy(logger, "log_debug_stack_trace")

    @only_raise_attribute_error
    def fn():
        raise ValueError("foo bar error")

    with pytest.raises(AttributeError, match="foo bar error"):
        fn()

    assert spy.call_count


def test_only_raise_attribute_error_when_already_raises(mocker, ape_caplog):
    spy = mocker.spy(logger, "log_debug_stack_trace")

    @only_raise_attribute_error
    def fn():
        raise AttributeError("foo bar error")

    with pytest.raises(AttributeError, match="foo bar error"):
        fn()

    # Does not log because is already an attr err
    assert not spy.call_count


def test_dependency_manager():
    actual = ManagerAccessMixin.dependency_manager
    assert isinstance(actual, DependencyManager)
