from typing import TYPE_CHECKING, Any

from hypothesis.strategies import SearchStrategy

from ape.utils import cached_property
from hypothesis import given

from ..contextmanagers import RevertsContextManager

from .types import TestModifier
from .base import BaseTestItem

if TYPE_CHECKING:
    from ethpm_types.abi import ABIType

    from ape.api.accounts import TestAccountAPI
    from ape.contracts import ContractInstance
    from ethpm_types.abi import MethodABI

    from ape.contracts.base import ContractTransactionHandler


class ContractTestItem(BaseTestItem):
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

    def execute_test(self, *call_args):
        assert self.executor.delegate == self.delegate, "Why does this not raise when it should?"

        # TODO: Control snapshot of start via `TestModifier.TEST_AFTER`?
        with self.chain_manager.isolate():
            if raw_revert_msg := self.modifiers.get(TestModifier.CHECK_REVERTS):
                reverts_message = self.eval_arg(raw_revert_msg)
                with RevertsContextManager(reverts_message):
                    self.method(*call_args, sender=self.executor)

            else:
                # NOTE: Let revert bubble up naturally
                receipt = self.method(*call_args, sender=self.executor)

                if raw_event_logs := self.modifiers.get(TestModifier.CHECK_EMITS):
                    expected_events = list(map(self.eval_arg, raw_event_logs))
                    assert receipt.events == expected_events

                # TODO: Test reporting functionality?

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

    def eval_arg(self, raw_arg: str) -> Any:
        # Just eval the whole string w/ global/local context from case
        # NOTE: This is potentially dangerous, but only run on your own tests!
        return eval(raw_arg, self.call_context, self.call_args)

    def runtest(self):
        """Collect call args and execute test. Convert to fuzz test if applicable."""

        given_args: dict[str, SearchStrategy] = {}
        for arg_name, arg in self.call_args.items():
            if isinstance(arg, SearchStrategy):
                given_args[arg_name] = arg

        def test_case(**kwargs):
            # NOTE: Retain ordering from original call args,
            #       but update SearchStrategy for concrete example
            args = {k: kwargs.get(k, v) for k, v in self.call_args.items()}
            self.execute_test(*args.values())

        if given_args:
            # NOTE: Re-write as a fuzzing case (leveraging Hypothesis integration)
            test_case = given(**given_args)(self.hypothesis_settings(test_case))

        test_case()
