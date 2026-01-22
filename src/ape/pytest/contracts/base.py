from typing import TYPE_CHECKING, Any

import pytest
from _pytest.fixtures import TopRequest

from ape.utils import ManagerAccessMixin, cached_property

from .types import TestModifier

if TYPE_CHECKING:
    from ethpm_types import ContractType
    from ethpm_types.abi import ABIType
    from hypothesis import settings as HypothesisSettings

    from ape.api.accounts import TestAccountAPI
    from ape.contracts import ContractInstance


# TODO: Configure EVM context? Pre-compiles? Foundry-like cheatcodes?


class BaseTestItem(pytest.Item, ManagerAccessMixin):
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
        settings_kwargs: dict = {}

        if max_examples := self.modifiers.get(TestModifier.FUZZ_MAX_EXAMPLES):
            settings_kwargs["max_examples"] = max_examples

        if deadline := self.modifiers.get(TestModifier.FUZZ_DEADLINE):
            settings_kwargs["deadline"] = deadline

        from hypothesis import settings

        return settings(**settings_kwargs)

    @property
    def executor(self) -> "TestAccountAPI":
        return self.account_manager.test_accounts[-1]

    @cached_property
    def instance(self) -> "ContractInstance":
        """
        The instance of `contract_type` to use for test case(s) found in contract test module.

        ```{important}
        This will snapshot the instance's deployment so that each case can restart just after.
        ```

        ```{note}
        If the module has `setUp` method, that will be called before snapshotting the instance.
        ```
        """
        if hasattr(instance := self.executor.deploy(self.contract_type), "setUp"):
            instance.setUp(sender=self.executor)

        self.snapshot = self.chain_manager.snapshot()
        return instance

    @cached_property
    def call_context(self) -> dict:
        return {
            # 1. Contract instance (document not to use bare storage or internal calls)
            # Solidity instance (document not to use without `this.`)
            "this": self.instance,
            # Vyper instance
            "self": self.instance,
            # 2. Ape stuff
            "msg": type(
                "MsgContext",
                (object,),
                {"sender": self.executor},
                # TODO: Other parts of `msg.` context?
            ),
            # TODO: Other evm stuff? e.g. `tx`, `block`, etc.
        }

    def get_value(self, abi_type: "ABIType") -> Any:
        assert abi_type.name  # mypy happy (always true)
        if abi_type.name == "vm":
            # NOTE: Foundry stdlib's VM instance
            return "0x7109709ECfa91a80626fF3989D68f67F5b1DD12D"

        elif abi_type.name == "executor":
            return self.executor

        elif fixture_value := self.get_fixture_value(abi_type.name):
            return fixture_value

        # NOTE: Returning a Hypothesis strategy automatically converts to a fuzz tests
        from eth_abi.tools import get_abi_strategy

        return get_abi_strategy(abi_type.canonical_type)
