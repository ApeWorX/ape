import re
from re import Pattern
from typing import Optional, Union

from ethpm_types.abi import ErrorABI

from ape.contracts import ContractInstance
from ape.exceptions import ContractLogicError, CustomError, TransactionError
from ape.utils.basemodel import ManagerAccessMixin

_RevertMessage = Union[str, re.Pattern]


class RevertInfo:
    """
    Similar to ``pytest.ExceptionInfo``.
    Returned by ``RevertsContextManager.__enter__()``.
    """

    # NOTE: Type ignore because it is only None internally
    # and not when the user needs to access it.
    value: ContractLogicError = None  # type: ignore


class RevertsContextManager(ManagerAccessMixin):
    def __init__(
        self,
        expected_message: Optional[Union[_RevertMessage, type[CustomError], ErrorABI]] = None,
        dev_message: Optional[_RevertMessage] = None,
        **error_inputs,
    ):
        self.expected_message = expected_message
        self.dev_message = dev_message
        self.error_inputs = error_inputs
        self.revert_info: Optional[RevertInfo] = None

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
            err_message = "Could not find the source of the revert."

            # Attempt to show source traceback so the user can see the real failure.
            if (info := self.revert_info) and (ex := info.value):
                if tb := ex.source_traceback:
                    err_message = f"{err_message}\n{tb}"

            raise AssertionError(err_message)

        if not (
            (self.dev_message.match(dev_message) is not None)
            if isinstance(self.dev_message, re.Pattern)
            else (dev_message == self.dev_message)
        ):
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

    def _check_custom_error(self, exception: Union[CustomError]):
        expected_error_cls = self.expected_message

        if not isinstance(expected_error_cls, ErrorABI) and not isinstance(
            expected_error_cls, type
        ):
            # Not expecting a custom error type.
            return

        elif (
            isinstance(expected_error_cls, type)
            and issubclass(expected_error_cls, CustomError)
            and not isinstance(exception, expected_error_cls)
            and isinstance(getattr(expected_error_cls, "contract", None), ContractInstance)
        ):
            # NOTE: This is the check that ensures the error class is coming from
            # the expected contract instance (e.g. from the same address).
            # If not address is being compared, this check is skipped.

            raise AssertionError(
                f"Expected error '{expected_error_cls.__name__}' "
                f"but was '{type(exception).__name__}'"
            )

        if not self.error_inputs:
            return

        # Making assertions on inputs to error.
        incorrect_values = []

        actual_error_inputs = exception.inputs
        for ipt_name, expected_ipt in self.error_inputs.items():
            if ipt_name not in actual_error_inputs:
                # Assertion is not being made on this input.
                continue

            actual_ipt = actual_error_inputs[ipt_name]
            if actual_ipt != expected_ipt:
                incorrect_values.append(
                    f"Expected input '{ipt_name}' to be '{expected_ipt}' but was '{actual_ipt}'."
                )

        if incorrect_values:
            raise AssertionError("\n".join(incorrect_values))

    def __enter__(self, *args, **kwargs):
        info = RevertInfo()
        self.revert_info = info
        return info

    def __exit__(self, exc_type: type, exc_value: Exception, traceback) -> bool:
        if exc_type is None:
            raise AssertionError("Transaction did not revert.")

        if not isinstance(exc_value, ContractLogicError):
            raise AssertionError(
                f"Transaction did not revert.\n"
                f"However, an exception of type {type(exc_value)} occurred: {exc_value}."
            ) from exc_value

        # Set the exception on the returned info.
        # This allows the user to make further assertions on the exception.
        if self.revert_info is not None:
            self.revert_info.value = exc_value

        if self.dev_message is not None:
            self._check_dev_message(exc_value)

        if self.expected_message is not None and isinstance(self.expected_message, (str, Pattern)):
            self._check_expected_message(exc_value)

        elif self.expected_message is not None and isinstance(exc_value, CustomError):
            # Is a custom error type.
            self._check_custom_error(exc_value)

        # Returning True causes the expected exception not to get raised
        # and the test to pass
        return True
