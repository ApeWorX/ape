from typing import TYPE_CHECKING, Any

import pytest
from hypothesis import given
from hypothesis.strategies import SearchStrategy

from ape.pytest.contextmanagers import RevertsContextManager
from ape.utils import cached_property

from .base import BaseTestItem
from .types import TestModifier

if TYPE_CHECKING:
    from ethpm_types.abi import ABIType, MethodABI

    from ape.api.accounts import TestAccountAPI
    from ape.contracts import ContractInstance
    from ape.contracts.base import ContractTransactionHandler
    from ape.types.vm import SnapshotID


class ContractTestItem(BaseTestItem):
    """
    A single functional ``test*`` method from a contract module.

    Supports ``@custom:ape-test-after`` chains: followers inherit world/chain state
    from their predecessor, and the chain restores to the root snapshot after the
    last segment finishes (pass or fail).
    """

    # Wired by ``ordering.topological_sort`` during collection.
    predecessor_item: "ContractTestItem | None" = None
    chain_root: "ContractTestItem | None" = None
    chain_dependents: list["ContractTestItem"]
    _ape_test_outcome: str | None = None
    _chain_snapshot_id: "SnapshotID | None" = None
    _chain_pending: set[str] | None = None

    def __init__(
        self,
        *,
        abi: "MethodABI",
        parametrized_args: dict | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)

        self.abi = abi
        self.parametrized_args = parametrized_args or {}
        self.chain_dependents = []

    @cached_property
    def executor(self) -> "TestAccountAPI":
        return self.load_executor(self.modifiers.get(TestModifier.TEST_EXECUTOR))

    @property
    def contract(self) -> "ContractInstance":
        return self.chain_manager.contracts.instance_at(
            self.executor.address,
            contract_type=self.contract_type,
        )

    @property
    def call_context(self) -> dict:
        return {
            "msg": type(
                "Msg",
                (object,),
                {"sender": self.executor},
            ),
        }

    @property
    def method(self) -> "ContractTransactionHandler":
        return getattr(self.contract, self.abi.name)

    def get_value(self, abi_type: "ABIType") -> Any:
        # NOTE: Overrides BaseTestItem impl to also check parametrized case args
        if parameterized_value := self.parametrized_args.get(abi_type.name):
            return parameterized_value

        return super().get_value(abi_type)

    @cached_property
    def call_args(self) -> dict[str, Any]:
        """The args for calling the method in this specific case"""

        if any(ipt.name is None for ipt in self.abi.inputs):
            raise RuntimeError(f"All input arguments in '{self}' must have a name.")

        return {ipt.name: self.get_value(ipt) for ipt in self.abi.inputs if ipt.name is not None}

    def eval_arg(self, raw_arg: str, **call_args) -> Any:
        # Just eval the whole string w/ global/local context from case
        # NOTE: This is potentially dangerous, but only run on your own tests!
        return eval(raw_arg, self.call_context, call_args)

    @property
    def is_chain_follower(self) -> bool:
        return self.predecessor_item is not None

    @property
    def _isolation_enabled(self) -> bool:
        runner = getattr(type(self), "_test_runner", None) or getattr(self, "_test_runner", None)
        if runner is None:
            return True
        return bool(runner.config_wrapper.isolation)

    def setup(self) -> None:
        """Apply ``TEST_AFTER`` skip policy and take the chain-root snapshot."""
        super().setup()

        # Contract-test chains own snapshot policy; avoid pytest function isolation
        # wiping shared chain state between ordered segments if it is ever injected.
        if "_function_isolation" in self.fixturenames:
            self.fixturenames = [n for n in self.fixturenames if n != "_function_isolation"]

        if self.is_chain_follower:
            pred = self.predecessor_item
            assert pred is not None
            outcome = pred._ape_test_outcome
            if outcome != "passed":
                reason = f"Predecessor '{pred.name}' did not pass"
                if outcome:
                    reason = f"{reason} (outcome={outcome})"
                else:
                    reason = f"{reason} (not run)"
                pytest.skip(reason)
            return

        # Root / standalone: resolve fixtures first so session-scoped deploys
        # (e.g. ``token``) are included in the snapshot, then snapshot.
        if self._isolation_enabled:
            _ = self.call_args
            snapshot_id = self.chain_manager.snapshot()
            self._chain_snapshot_id = snapshot_id
            root = self.chain_root or self
            root._chain_snapshot_id = snapshot_id

    def teardown(self) -> None:
        """Restore the chain-root snapshot once the last segment finishes."""
        try:
            if not self._isolation_enabled:
                return

            pending = self._chain_pending
            root = self.chain_root or self
            snapshot_id = root._chain_snapshot_id
            if snapshot_id is None:
                return

            if pending is not None:
                pending.discard(self.nodeid)
                if pending:
                    return

            try:
                self.chain_manager.restore(snapshot_id)
            except Exception:  # noqa: BLE001
                from ape.logging import logger

                logger.debug("Failed to restore contract-test chain snapshot.", exc_info=True)
            finally:
                root._chain_snapshot_id = None
        finally:
            super().teardown()

    def execute_test(self, **given_kwargs):
        # NOTE: Retain ordering from original call args,
        #       but update SearchStrategy for concrete example
        call_args = {k: given_kwargs.get(k, v) for k, v in self.call_args.items()}
        calldata = self.method.encode_input(*call_args.values())

        with self.executor.delegate_to(self.delegate, receiver=0x1) as delegate:
            if raw_revert_msg := self.modifiers.get(TestModifier.CHECK_REVERTS):
                with RevertsContextManager(raw_revert_msg):
                    delegate(data=calldata)

            else:
                receipt = delegate(data=calldata)

                if raw_event_logs := self.modifiers.get(TestModifier.CHECK_EMITS):
                    expected_events = [self.eval_arg(r, **call_args) for r in raw_event_logs]
                    assert receipt.events == expected_events

            # TODO: Test reporting functionality?

    def runtest(self):
        """Collect call args and execute test. Convert to fuzz test if applicable."""

        given_args: dict[str, SearchStrategy] = {}
        for arg_name, arg in self.call_args.items():
            if isinstance(arg, SearchStrategy):
                given_args[arg_name] = arg

        test_case = self.execute_test

        if given_args:
            # NOTE: Re-write as a fuzzing case (leveraging Hypothesis integration)
            test_case = self.hypothesis_settings(given(**given_args)(test_case))

        test_case()
