import pytest

from ape.exceptions import ProviderNotConnectedError
from ape.logging import logger
from ape.managers.project import DependencyManager
from ape.utils.basemodel import DiskCacheableModel, ManagerAccessMixin, only_raise_attribute_error
from ape.utils.os import create_tempdir


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


class TestDiskCacheableModel:
    @pytest.fixture(scope="class")
    def ExampleModel(self):
        class _ExampleModel(DiskCacheableModel):
            aa: int
            bb: str
            cc: dict[str, dict[str, int]]

        return _ExampleModel

    def test_model_validate_file(self, ExampleModel):
        with create_tempdir() as path:
            file = path / "example.json"
            json_str = '{"aa":123,"bb":"Hello Pydantic!","cc":{"1":{"2":3}}}'
            file.write_text(json_str)
            instance = ExampleModel.model_validate_file(file)
            file.unlink()

        assert instance.aa == 123
        assert instance.bb == "Hello Pydantic!"
        assert instance.cc == {"1": {"2": 3}}
        # Show the path was already set.
        assert instance._path == file

    def test_model_dump_file(self, ExampleModel):
        instance = ExampleModel(aa=123, bb="Hello Pydantic!", cc={"1": {"2": 3}})
        expected = '{"aa":123,"bb":"Hello Pydantic!","cc":{"1":{"2":3}}}'
        with create_tempdir() as path:
            file = path / "example.json"
            instance.model_dump_file(file)
            actual = file.read_text()

        assert actual == expected
