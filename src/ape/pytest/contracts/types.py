from enum import Enum
from typing import Any


class TestModifier(str, Enum):
    """
    Enum that represents custom natspec annotations supported by Ape's Contract Test feature.

    These will be automatically parsed into `ContractTestModule.modifiers`
    and `BaseContractTest.modifiers`, for use in modifying test handling.
    """

    # Test result checking modifiers
    CHECK_REVERTS = "custom:ape-check-reverts"
    CHECK_EMITS = "custom:ape-check-emits"

    # Test harness setup modifiers
    MARK_PARAMETRIZE = "custom:ape-mark-parametrize"
    MARK_XFAIL = "custom:ape-mark-xfail"

    # TODO: Support others?
    # TODO: Fork testing? Marker for using different networks?
    #       (e.g. `@custom:ape-mark-fork ethereum:mainnet`)

    # Fuzz harness setup modifiers
    FUZZ_MAX_EXAMPLES = "custom:ape-fuzzer-max-examples"
    FUZZ_DEADLINE = "custom:ape-fuzzer-deadline"

    # Stateful harness setup modifiers
    STATEFUL_STEP_COUNT = "custom:ape-stateful-step-count"
    STATEFUL_BUNDLES = "custom:ape-stateful-bundles"
    STATEFUL_TARGETS = "custom:ape-stateful-targets"
    STATEFUL_CONSUMES = "custom:ape-stateful-consumes"

    @classmethod
    def parse_modifier_args(cls, natspecs: dict) -> dict["TestModifier", Any]:
        """Return the mapping of (supported) custom modifiers to their parsed args"""

        modifiers: dict[TestModifier, Any] = {}
        for natspec in natspecs:
            if not natspec.startswith("custom:"):
                continue

            try:
                modifier = cls(natspec)

            except Exception as e:
                from ape.logging import logger

                all_modifiers = "', '".join(e.value for e in cls)
                logger.warn_from_exception(
                    e, f"Unknown modifier {natspec}. Must be one of '{all_modifiers}'."
                )
                continue

            modifiers[modifier] = modifier.parse_args(natspecs[natspec])

        return modifiers

    def __str__(self) -> str:
        return self.value

    def _split_args(self, raw_args: str) -> list[str]:
        # Examples:
        #   1. Only one arg on same line: "..."
        #   @custom:ape-check-reverts ...
        #   2. No arg on same line, but multiple after: "- ... - ..."
        #   @custom:ape-check-emits
        #   - ...
        #   - ...
        #   3. Arg on same line, and multiple after: "... - ... - ..."
        #   @custom:ape-mark-parametrize ...
        #   - ...
        #   - ...
        # TODO: Does `Solidity` parse them this same way? Should it be per compiler plugin?

        if not raw_args:
            return []

        # NOTE: Do `.lstrip("-")` on `raw_args` to remove first instance of `-`
        #       **in scenarios where we don't have an arg on the same line first**.
        return [ln.strip() for ln in raw_args.lstrip("-").split("-")]

    def parse_args(self, args: str) -> Any:
        match self:
            case TestModifier.CHECK_REVERTS:
                return args

            case TestModifier.CHECK_EMITS:
                return self._split_args(args)

            case TestModifier.MARK_PARAMETRIZE:
                parameters, *raw_cases = self._split_args(args)
                case_tuples = [eval(a, {}, {}) for a in raw_cases]
                if not any(isinstance(i, tuple) for i in case_tuples):
                    assert "," not in parameters
                    return {parameters: case_tuples}

                return dict(
                    zip(
                        parameters.split(","),
                        # NOTE: Must be context-independent values to eval
                        list(zip(*case_tuples, strict=True)),
                        strict=True,
                    )
                )

            case TestModifier.MARK_XFAIL:
                return args

            case TestModifier.FUZZ_MAX_EXAMPLES:
                return int(args)

            case TestModifier.FUZZ_DEADLINE:
                return int(args)

            case TestModifier.STATEFUL_STEP_COUNT:
                return int(args)

            case TestModifier.STATEFUL_BUNDLES:
                return args.split(" ")

            case TestModifier.STATEFUL_CONSUMES:
                return set(args.split(" "))

            case TestModifier.STATEFUL_TARGETS:
                return args
