from typing import TYPE_CHECKING, Any

import pytest

from ape.utils import ManagerAccessMixin, cached_property

from .types import TestModifier

if TYPE_CHECKING:
    from collections.abc import Iterator

    from ethpm_types import ContractType
    from ethpm_types.abi import MethodABI


    from .base import BaseTestItem


class ContractTestModule(pytest.Collector, ManagerAccessMixin):
    def __init__(self, *, contract_type: "ContractType", **kwargs):
        super().__init__(**kwargs)
        self.contract_type = contract_type

    @cached_property
    def contract_modifiers(self) -> dict[TestModifier, Any]:
        return TestModifier.parse_modifier_args(self.contract_type.devdoc)

    def get_method_modifiers(self, abi: "MethodABI") -> dict[TestModifier, Any]:
        modifiers = TestModifier.parse_modifier_args(
            self.contract_type.devdoc.get("methods", {}).get(abi.selector, {})
        )
        # NOTE: Cascade such that method-level overrides contract-level
        modifiers.update({k: v for k, v in self.contract_modifiers.items() if k not in modifiers})
        return modifiers

    def collect(self) -> "Iterator[BaseTestItem]":
        if any(abi.name.startswith("rule") for abi in self.contract_type.mutable_methods):
            # It is a stateful test, so the whole module is a single item
            from .stateful import StatefulTestItem

            yield StatefulTestItem.from_parent(
                self,
                name=self.name,
                contract_type=self.contract_type,
                modifiers=self.contract_modifiers,
            )
            return

        from .functional import ContractTestItem

        # NOTE: Only mutable calls that have names starting with `test_` will work
        for abi in self.contract_type.mutable_methods:
            if abi.name.startswith("test"):
                # 1. First parse the natspec for that test to obtain any `@custom:ape-*` modifiers
                modifiers = self.get_method_modifiers(abi)

                # 2. Yield test cases (multiple if `mark.parametrize` exists)
                if parametrized_args := modifiers.get(TestModifier.MARK_PARAMETRIZE):
                    # NOTE: If no cases collected, will not collect anything (fails silently)
                    for case_args in zip(*parametrized_args.values(), strict=True):
                        parametrized_str = "-".join(map(str, case_args))
                        yield ContractTestItem.from_parent(
                            self,
                            name=f"{self.name}.{abi.name}[{parametrized_str}]",
                            contract_type=self.contract_type,
                            modifiers=modifiers,
                            parametrized_args=dict(
                                zip(parametrized_args.keys(), case_args, strict=True)
                            ),
                            abi=abi,
                        )

                else:
                    yield ContractTestItem.from_parent(
                        self,
                        name=f"{self.name}.{abi.name}",
                        contract_type=self.contract_type,
                        modifiers=modifiers,
                        abi=abi,
                    )
