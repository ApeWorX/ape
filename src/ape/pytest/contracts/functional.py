from typing import TYPE_CHECKING, Any

from hypothesis.strategies import SearchStrategy

from ape.utils import cached_property
from hypothesis import given

from ..contextmanagers import RevertsContextManager

from .types import TestModifier
from .base import BaseTestItem

if TYPE_CHECKING:
    from ethpm_types.abi import MethodABI, ABIType

    from ape.contracts import ContractMethodHandler


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
    def method(self) -> "ContractMethodHandler":
        return getattr(self.instance, self.abi.name)

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
        given_args: dict[str, SearchStrategy] = {}
        for arg_name in (call_args := self.call_args):
            if isinstance(arg := call_args[arg_name], SearchStrategy):
                given_args[arg_name] = arg
                call_args[arg_name] = None  # NOTE: Placeholder for later update

        def test_case(**kwargs):
            # NOTE: We need to retain ordering using the original dict
            args = {k: v if v is not None else kwargs[k] for k, v in call_args.items()}

            if raw_revert_msg := self.modifiers.get(TestModifier.CHECK_REVERTS):
                reverts_message = self.eval_arg(raw_revert_msg)
                with RevertsContextManager(reverts_message):
                    self.method(
                        *args.values(),
                        sender=self.executor,
                    )

            else:
                # NOTE: Let revert bubble up naturally
                receipt = self.method(
                    *args.values(),
                    sender=self.executor,
                )

                if raw_event_logs := self.modifiers.get(TestModifier.CHECK_EMITS):
                    expected_events = list(map(self.eval_arg, raw_event_logs))
                    assert receipt.events == expected_events

                # TODO: Test reporting functionality?

        if given_args:
            # NOTE: Re-write as a fuzzing case (leveraging Hypothesis integration)
            test_case = given(**given_args)(self.hypothesis_settings(test_case))

        test_case()
