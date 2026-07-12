from collections.abc import Callable
from types import new_class
from typing import TYPE_CHECKING, Any

from ape.utils import cached_property
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
            (self.contract_type.devdoc or {}).get("methods", {}).get(abi.selector, {})
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
                f"'{self.name}:{abi.name}' must return exactly 1 value to target bundle."
            )

        # NOTE: `Bundle` is by default "falsey", use explicit `is None` check
        elif (target := self.bundles.get(bundle_name)) is None:
            raise AssertionError(
                f"'{self.name}:{abi.name}' targets unrecognized bundle '{bundle_name}'."
            )

        return target

    def consumes(self, abi: "MethodABI") -> set[str]:
        if not (modifiers := self.get_method_modifiers(abi)):
            return set()

        elif not (bundle_names := modifiers.get(TestModifier.STATEFUL_CONSUMES)):
            return set()

        elif unrecognized_bundles := "', '".join(bundle_names - set(self.bundles)):
            raise AssertionError(
                f"'{self.name}:{abi.name}' consumes unknown bundle(s) '{unrecognized_bundles}'."
            )

        elif missing_args := "', '".join(bundle_names - set(ipt.name for ipt in abi.inputs)):
            raise AssertionError(
                f"'{self.name}:{abi.name}' missing arg(s) to consume bundle(s): '{missing_args}'."
            )

        return bundle_names

    def get_call_args(self, abi: "MethodABI") -> dict:
        call_args: dict = {}

        for ipt in abi.inputs:
            if not ipt.name:
                raise AssertionError(f"Function '{abi.name}' has anonymous inputs.")

            elif ipt.name in iter(self.bundles):
                call_args[ipt.name] = None  # Placeholder for `rule`

            elif isinstance(value := self.get_value(ipt), st.SearchStrategy):
                call_args[ipt.name] = None  # Placeholder for `rule`

            else:
                call_args[ipt.name] = value

        return call_args

    def call_method(self, abi: "MethodABI") -> Callable:
        call_args = self.get_call_args(abi)

        executor = self.load_executor(
            self.get_method_modifiers(abi).get(TestModifier.TEST_EXECUTOR)
        )
        contract = self.chain_manager.contracts.instance_at(
            executor.address,
            contract_type=self.contract_type,
        )
        method = getattr(contract, abi.name)

        if abi.stateMutability == "nonpayable":  # (e.g. `initializes`, `rule`)
            # NOTE: This is passed through to another class instance, `self` is treated differently
            def wrapped_method(self: RuleBasedStateMachine, **kwargs):
                # NOTE: Maintain proper ordering from `call_args`
                args = {k: kwargs.get(k, v) for k, v in call_args.items()}

                # TODO: How to handle providing other txn_kwargs like `value=`?
                receipt = method(*args.values(), sender=executor)

                if isinstance(result := receipt.return_value, list):
                    return multiple(*result)

                # NOTE: Avoid returning empty tuple, when `None` expected
                return result or None

        else:  # view/pure (e.g. `invariant`)
            # NOTE: This is passed through to another class instance, `self` is treated differently
            def wrapped_method(self: RuleBasedStateMachine, **kwargs):
                # NOTE: Maintain proper ordering from `call_args`
                args = {k: kwargs.get(k, v) for k, v in call_args.items()}

                if isinstance(result := method(*args.values()), list):
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
                    loc = f"{self.path}:{self.contract_type.name}.{abi.name}"
                    raise AssertionError(
                        f"'{loc}' needs to target a bundle using `@custom:ape-stateful-targets`"
                    )

                initializers[abi.name] = initialize(target=target)(self.call_method(abi))

        return initializers

    @cached_property
    def rules(self) -> dict[str, Rule]:
        rules: dict[str, Rule] = {}
        for abi in self.contract_type.mutable_methods:
            if abi.name.startswith("rule"):
                decorator_args: dict[str, st.SearchStrategy] = {}

                if (target := self.get_target(abi)) is not None:
                    decorator_args["target"] = target

                for ipt in abi.inputs:
                    if not ipt.name:
                        raise AssertionError(f"Function '{abi.name}' has anonymous inputs.")

                    if (bundle := self.bundles.get(ipt.name)) is not None:
                        if ipt.name in self.consumes(abi):
                            bundle = consumes(bundle)

                        if "[" in ipt.canonical_type:
                            # TODO: Figure out if static or dynamic array?
                            # TODO: Figure out how to specify max array size for vyper?
                            bundle = st.lists(bundle, max_size=10)

                        decorator_args[ipt.name] = bundle

                    elif isinstance(strategy := self.get_value(ipt), st.SearchStrategy):
                        decorator_args[ipt.name] = strategy

                    # else: else we don't want add a non-strategy to the decorator

                    # TODO: Support preconditions?

                rules[abi.name] = rule(**decorator_args)(self.call_method(abi))  # type: ignore[call-overload]

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
        chain_manager = self.chain_manager

        # NOTE: Inject needed class variables here
        class StatefulTestCase(RuleBasedStateMachine):
            # Add necessary **read-only** attributes for our test to use
            contract_type = self.contract_type

            def __init__(self):
                super().__init__()
                self.snapshot = chain_manager.snapshot()

            def teardown(self):
                chain_manager.restore(self.snapshot)

        def add_fields(ns):
            ns.update(self.bundles)
            ns.update(self.initializers)
            ns.update(self.rules)
            ns.update(self.invariants)

        return new_class(
            self.name,
            (StatefulTestCase, RuleBasedStateMachine),
            exec_body=add_fields,
        )

    def runtest(self):
        run_state_machine_as_test(
            self.state_machine,
            settings=self.hypothesis_settings,
        )
