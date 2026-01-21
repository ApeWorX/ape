from collections.abc import Callable
from types import new_class
from typing import TYPE_CHECKING, Any

from ape.utils import cached_property
from eth_abi.tools import get_abi_strategy
from hypothesis import strategies as st
from hypothesis.stateful import (
    Bundle,
    Rule,
    RuleBasedStateMachine,
    consumes,
    initialize,
    invariant,
    multiple,
    rule,
    run_state_machine_as_test,
)

from .base import BaseTestItem
from .types import TestModifier

if TYPE_CHECKING:
    from ethpm_types.abi import MethodABI


class StatefulTestItem(BaseTestItem):
    def get_method_modifiers(self, abi: "MethodABI") -> dict[TestModifier, Any]:
        modifiers = TestModifier.parse_modifier_args(
            self.contract_type.devdoc.get("methods", {}).get(abi.selector, {})
        )
        # NOTE: Cascade such that method-level overrides contract-level
        modifiers.update({k: v for k, v in self.modifiers.items() if k not in modifiers})
        return modifiers

    @cached_property
    def bundles(self) -> dict[str, Bundle]:
        # Check contract-level Natspec for bundle definitions
        if not (names := self.modifiers.get(TestModifier.STATEFUL_BUNDLES)):
            return {}

        return {name: Bundle(name) for name in names}

    def get_target(self, abi: "MethodABI") -> Bundle | None:
        if not (modifiers := self.get_method_modifiers(abi)):
            return None

        elif not (bundle_name := modifiers.get(TestModifier.STATEFUL_TARGETS)):
            return None

        elif len(abi.outputs) != 1:
            raise AssertionError(
                f"'{self.path}:{abi.name}' must return exactly 1 value for bundle."
            )

        elif (target := self.bundles.get(bundle_name)) is None:
            raise AssertionError(
                f"'{self.path}:{abi.name}' has unrecognized bundle: '{bundle_name}'."
            )

        return target

    def consumes(self, abi: "MethodABI") -> set[str]:
        if not (modifiers := self.get_method_modifiers(abi)):
            return set()

        elif not (bundle_names := modifiers.get(TestModifier.STATEFUL_CONSUMES)):
            return set()

        elif unrecognized_bundles := "', '".join(bundle_names - set(self.bundles)):
            raise AssertionError(
                f"'{self.path}:{abi.name}' has unrecognized bundle(s): '{unrecognized_bundles}'."
            )

        elif unrecognized_args := "', '".join(bundle_names - set(ipt.name for ipt in abi.inputs)):
            raise AssertionError(
                f"'{self.path}:{abi.name}' arg(s) reference unknown bundle(s): '{unrecognized_args}'."
            )

        return bundle_names

    def call_method(self, abi: "MethodABI") -> Callable:
        if abi.stateMutability == "nonpayable":

            def wrapped_method(_: RuleBasedStateMachine, **kwargs):
                method = self.instance._mutable_methods_[abi.name]
                # TODO: Do we do proper lookup by name for value location?
                # TODO: How to handle providing other txn_kwargs like `value=`?
                receipt = method(*kwargs.values(), sender=self.executor)

                if isinstance(result := receipt.return_value, list):
                    return multiple(*result)

                # NOTE: Avoid returning empty tuple, when `None` expected
                return result or None

        else:  # view/pure (e.g. `invariant`)

            def wrapped_method(_: RuleBasedStateMachine, **kwargs):
                method = self.instance._view_methods_[abi.name]
                if isinstance(result := method(*kwargs.values()), list):
                    return multiple(*result)

                # NOTE: Avoid returning empty tuple, when `None` expected
                return result or None

        wrapped_method.__name__ = abi.name
        return wrapped_method

    @cached_property
    def initializers(self) -> dict[str, Callable]:
        initializers: dict[str, Callable] = {}
        for abi in self.contract_type.mutable_methods:
            if abi.name.startswith("initialize"):
                if (target := self.get_target(abi)) is None:
                    raise AssertionError(
                        f"'{self.path}:{abi.name}' needs to target a bundle w/ `@custom:ape-stateful-targets`"
                    )

                initializers[abi.name] = initialize(target=target)(self.call_method(abi))

        return initializers

    @cached_property
    def rules(self) -> dict[str, Rule]:
        # TODO: Support preconditions?
        rules: dict[str, Rule] = {}
        for abi in self.contract_type.mutable_methods:
            if abi.name.startswith("rule"):
                decorator_args = {}
                for ipt in abi.inputs:
                    if (bundle := self.bundles.get(ipt.name)) is not None:
                        if ipt.name in self.consumes(abi):
                            bundle = consumes(bundle)

                        if "[" in ipt.canonical_type:
                            # TODO: Figure out how to specify max array size for vyper
                            bundle = st.lists(bundle, max_size=10)

                        decorator_args[ipt.name] = bundle

                    else:
                        decorator_args[ipt.name] = get_abi_strategy(ipt.canonical_type)

                if (target := self.get_target(abi)) is not None:
                    decorator_args["target"] = target

                rules[abi.name] = rule(**decorator_args)(self.call_method(abi))

        return rules

    @cached_property
    def invariants(self) -> dict[str, Callable]:
        # TODO: Support preconditions?
        return {
            abi.name: invariant()(self.call_method(abi))
            for abi in self.contract_type.view_methods
            if abi.name.startswith("invariant")
        }

    @cached_property
    def state_machine(self) -> type[RuleBasedStateMachine]:
        def add_fields(ns):
            ns.update(self.bundles)
            ns.update(self.initializers)
            ns.update(self.rules)
            ns.update(self.invariants)

        return new_class(
            self.name,
            (RuleBasedStateMachine,),
            exec_body=add_fields,
        )

    def runtest(self):
        run_state_machine_as_test(
            self.state_machine,
            settings=self.hypothesis_settings,
        )
