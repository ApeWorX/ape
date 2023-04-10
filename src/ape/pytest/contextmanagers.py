import re
from re import Pattern
from typing import Optional, Type, Union

from ape.contracts import ContractError
from ape.exceptions import ContractLogicError, TransactionError
from ape.utils.basemodel import ManagerAccessMixin

_RevertMessage = Union[str, re.Pattern]


class RevertsContextManager(ManagerAccessMixin):
    def __init__(
        self,
        expected_message: Optional[Union[_RevertMessage, ContractError]] = None,
        dev_message: Optional[_RevertMessage] = None,
        **error_inputs,
    ):
        self.expected_message = expected_message
        self.dev_message = dev_message
        self.error_inputs = error_inputs

    def _check_dev_message(self, exception: ContractLogicError):
        """
        Attempts to extract a dev-message from the contract source code by inspecting what
        instruction(s) led to a transaction revert.

        Raises:
            AssertionError: When the trace or source can not be retrieved, the dev message cannot
            be found, or the found dev message does not match the expected dev message.
        """

        try:
            dev_message = exception.dev_message
        except ValueError as err:
            raise AssertionError(str(err)) from err

        if dev_message is None:
            raise AssertionError("Could not find the source of the revert.")

        message_matches = (
            (self.dev_message.match(dev_message) is not None)
            if isinstance(self.dev_message, re.Pattern)
            else (dev_message == self.dev_message)
        )
        if not message_matches:
            assertion_error_message = (
                self.dev_message.pattern
                if isinstance(self.dev_message, re.Pattern)
                else self.dev_message
            )
            assertion_error_prefix = f"Expected dev revert message '{assertion_error_message}'"
            raise AssertionError(f"{assertion_error_prefix} but got '{dev_message}'.")

    def _check_expected_message(self, exception: ContractLogicError):
        """
        Compares the revert message given by the exception to the expected message.

        Raises:
            AssertionError: When the exception message is ``None`` or if the message does not match
            the expected message.
        """
        actual = exception.revert_message

        assertion_error_message = (
            self.expected_message.pattern
            if isinstance(self.expected_message, re.Pattern)
            else self.expected_message
        )

        assertion_error_prefix = f"Expected revert message '{assertion_error_message}'"

        message_matches = (
            (self.expected_message.match(actual) is not None)
            if isinstance(self.expected_message, re.Pattern)
            else (actual == self.expected_message)
        )

        if not message_matches:
            if actual == TransactionError.DEFAULT_MESSAGE:
                # The transaction failed without a revert message
                # but the user is expecting one.
                raise AssertionError(f"{assertion_error_prefix} but there was none.")

            raise AssertionError(f"{assertion_error_prefix} but got '{actual}'.")

    def _check_custom_error(self, exception: ContractLogicError):
        # NOTE: Type ignore because by now, we know the type is correct.
        expected: ContractError = self.expected_message  # type: ignore

        actual_name = exception.__class__.__name__
        expected_name = expected.name
        if actual_name != expected_name:
            raise AssertionError(f"Expected error '{expected_name}' but was '{actual_name}'")

        if self.error_inputs:
            # Making assertions on inputs to error.
            actual_inputs = getattr(exception, "input_data", {})

            incorrect_values = []
            for ipt_name, expected in self.error_inputs.items():
                if ipt_name not in actual_inputs:
                    # Assertion is not being made on this input.
                    continue

                actual = actual_inputs[ipt_name]
                if actual != expected:
                    incorrect_values.append(
                        f"Expected input '{ipt_name}' to be '{expected}' but was '{actual}'."
                    )

            if incorrect_values:
                raise AssertionError("\n".join(incorrect_values))

    def __enter__(self):
        pass

    def __exit__(self, exc_type: Type, exc_value: Exception, traceback) -> bool:
        if exc_type is None:
            raise AssertionError("Transaction did not revert.")

        if not isinstance(exc_value, ContractLogicError):
            raise AssertionError(
                f"Transaction did not revert.\n"
                f"However, an exception of type {type(exc_value)} occurred: {exc_value}."
            ) from exc_value

        if self.dev_message is not None:
            self._check_dev_message(exc_value)

        if self.expected_message is not None and isinstance(self.expected_message, (str, Pattern)):
            self._check_expected_message(exc_value)

        elif self.expected_message is not None:
            # Is a custom error type.
            self._check_custom_error(exc_value)

        # Returning True causes the expected exception not to get raised
        # and the test to pass
        return True
