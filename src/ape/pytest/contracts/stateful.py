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

        # Resolve once at rule construction; per-rule ``@custom:ape-test-executor``
        # may select a different account than the default (multiple delegated copies).
        executor = self.load_executor(
            self.get_method_modifiers(abi).get(TestModifier.TEST_EXECUTOR)
        )
        # Capture for closures — wrapped ``self`` is the Hypothesis state machine.
        delegate = self.delegate
        method_name = abi.name
        has_outputs = bool(abi.outputs)
        contracts = self.chain_manager.contracts
        contract_type = self.contract_type

        def _ensure_delegated(state_machine: RuleBasedStateMachine):
            """Sticky EIP-7702 delegate per executor for the life of this state machine."""
            active: dict = getattr(state_machine, "_ape_delegated_executors", None)
            if active is None:
                state_machine._ape_delegated_executors = active = {}
            if executor.address not in active:
                executor.set_delegate(delegate, receiver=0x1)
                active[executor.address] = executor
                # So Receipt.return_value / traces can resolve MethodABI at the EOA.
                # ``delegate_to`` intentionally does not cache; we do for the SM lifetime.
                contracts.cache_contract_type(executor.address, contract_type)

            from ape.contracts import ContractInstance

            return ContractInstance(executor.address, contract_type=contract_type)

        if abi.stateMutability == "nonpayable":  # (e.g. `initializes`, `rule`)
            # NOTE: This is passed through to another class instance, `self` is treated differently
            def wrapped_method(self: RuleBasedStateMachine, **kwargs):
                # NOTE: Maintain proper ordering from `call_args`
                args = {k: kwargs.get(k, v) for k, v in call_args.items()}

                # EIP-7702: run as executor (msg.sender == address(this) == executor),
                # matching ContractTestItem.execute_test.
                # TODO: How to handle providing other txn_kwargs like `value=`?
                delegated = _ensure_delegated(self)
                with executor.account_manager.use_sender(executor):
                    receipt = getattr(delegated, method_name)(*args.values())

                result = receipt.return_value if has_outputs else None
                if isinstance(result, (list, tuple)):
                    return multiple(*result)

                # NOTE: Avoid returning empty tuple, when `None` expected
                return result if result is not None else None

        else:  # view/pure (e.g. `invariant`)
            # NOTE: This is passed through to another class instance, `self` is treated differently
            def wrapped_method(self: RuleBasedStateMachine, **kwargs):
                # NOTE: Maintain proper ordering from `call_args`
                args = {k: kwargs.get(k, v) for k, v in call_args.items()}

                delegated = _ensure_delegated(self)
                with executor.account_manager.use_sender(executor):
                    result = getattr(delegated, method_name)(*args.values())

                if isinstance(result, (list, tuple)):
                    return multiple(*result)

                # NOTE: Avoid returning empty tuple, when `None` expected
                return result if result is not None else None

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
                self._ape_delegated_executors: dict = {}

            def teardown(self):
                # Clear sticky EIP-7702 delegates + temporary contract-type cache entries.
                for address, ex in list(getattr(self, "_ape_delegated_executors", {}).items()):
                    try:
                        ex.remove_delegate(receiver=0x1)
                    except Exception:  # noqa: BLE001
                        pass
                    try:
                        del chain_manager.contracts[address]
                    except Exception:  # noqa: BLE001
                        pass
                self._ape_delegated_executors.clear()
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
