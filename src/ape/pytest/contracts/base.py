from functools import cached_property
from typing import TYPE_CHECKING, Any, ClassVar, cast

from hypothesis import Phase
import pytest
from _pytest.fixtures import TopRequest

from ape.utils import ManagerAccessMixin

from .types import TestModifier

if TYPE_CHECKING:
    from ethpm_types import ContractType
    from ethpm_types.abi import ABIType
    from hypothesis import settings as HypothesisSettings
    from _pytest.nodes import Node

    from ape.contracts.base import ContractInstance
    from ape.api.accounts import TestAccountAPI
    from ape.types.vm import SnapshotID


# TODO: Configure EVM context? Pre-compiles? Foundry-like cheatcodes?


class BaseTestItem(pytest.Item, ManagerAccessMixin):
    # NOTE: Used to manage module-specific cache (to reduce deployments)
    _snapshots: ClassVar[dict["Node", "SnapshotID"]]

    def __init__(
        self,
        *,
        name: str,
        contract_type: "ContractType",
        modifiers: dict[TestModifier, Any],
        **kwargs,
    ):
        super().__init__(name=name, **kwargs)

        self.contract_type = contract_type
        self.modifiers = modifiers

        if xfail_reason := self.modifiers.get(TestModifier.MARK_XFAIL):
            self.add_marker(pytest.mark.xfail(reason=xfail_reason))

        # TODO: Figure out a more "official" way to get fixtures by name
        # HACK: Otherwise `.get_fixture_value` doesn't work
        # NOTE: Copied this from pytest's own python test runner
        fm = self.session._fixturemanager
        fixtureinfo = fm.getfixtureinfo(node=self, func=None, cls=None)
        self._fixtureinfo = fixtureinfo
        self.fixturenames = fixtureinfo.names_closure

    def get_fixture_value(self, fixture_name: str) -> Any | None:
        # NOTE: Use `_ispytest=True` to avoid `PytestDeprecationWarning`
        # TODO: Refactor to `SubRequest` (avoid typing error below)
        request = TopRequest(self, _ispytest=True)

        if fixture_defs := self.session._fixturemanager.getfixturedefs(fixture_name, self):
            return fixture_defs[0].execute(request)  # type: ignore[arg-type]

        return None

    @property
    def hypothesis_settings(self) -> "HypothesisSettings":
        settings_kwargs: dict = {
            # TODO: This really doesn't work well with shrinking, try to make it?
            #       (runs a *lot* faster without shrinking)
            "phases": [Phase.explicit, Phase.reuse, Phase.generate],
        }

        if max_examples := self.modifiers.get(TestModifier.FUZZ_MAX_EXAMPLES):
            settings_kwargs["max_examples"] = max_examples

        if deadline := self.modifiers.get(TestModifier.FUZZ_DEADLINE):
            settings_kwargs["deadline"] = deadline

        from hypothesis import settings

        return settings(**settings_kwargs)

    def get_value(self, abi_type: "ABIType") -> Any:
        assert abi_type.name  # mypy happy (always true)
        if (fixture_value := self.get_fixture_value(abi_type.name)) is not None:
            return fixture_value

        # NOTE: Returning a Hypothesis strategy automatically converts to a fuzz tests
        from eth_abi.tools import get_abi_strategy

        return get_abi_strategy(abi_type.canonical_type)

    @property
    def default_executor(self) -> "TestAccountAPI":
        # TODO: Handle xdist by providing multiple execution accounts? (one per process)
        return self.account_manager.test_accounts[-1]

    @cached_property
    def delegate(self) -> "ContractInstance":
        return self.default_executor.deploy(self.contract_type)

    def load_executor(self, executor_id: str | None) -> "TestAccountAPI":
        if not executor_id:
            executor = self.default_executor

        elif executor_id.isnumeric():
            executor = self.account_manager.test_accounts[int(executor_id)]

        elif not (executor := cast("TestAccountAPI", self.get_fixture_value(executor_id))):
            executor = self.account_manager[executor_id]

        from ape.api import AccountAPI

        if not isinstance(executor, AccountAPI):
            raise AssertionError(
                f"Fixture '{executor_id}' type must be a test account, not '{type(executor)}'."
            )

        if not self.contract_type.get_runtime_bytecode():
            raise AssertionError(f"'{self.contract_type.name}' does not provide a runtime.")

        # NOTE: "Caches" code delegations
        if executor.delegate != self.delegate:
            # NOTE: By default, `.set_delegate` targets `self` as receiver, which will fail
            executor.set_delegate(self.delegate, receiver=0x1)

        return executor

    @property
    def snapshot(self) -> "SnapshotID":
        assert self.parent, "Should never happen"  # mypy happy

        if not hasattr(self, "_snapshots"):
            self.__class__._snapshots = {}

        elif snapshot := self._snapshots.get(self.parent):
            return snapshot

        snapshot = self._snapshots[self.parent] = self.chain_manager.snapshot()
        return snapshot
