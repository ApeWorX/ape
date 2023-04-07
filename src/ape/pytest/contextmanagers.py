import re
from typing import Optional, Type, Union

from ape.exceptions import ContractLogicError, TransactionError
from ape.utils.basemodel import ManagerAccessMixin


class RevertsContextManager(ManagerAccessMixin):
    def __init__(
        self,
        expected_message: Optional[Union[str, re.Pattern]] = None,
        dev_message: Optional[Union[str, re.Pattern]] = None,
    ):
        self.expected_message = expected_message
        self.dev_message = dev_message

    def _check_dev_message(self, exception: ContractLogicError):
        """
        Attempts to extract a dev-message from the contract source code by inspecting what
        instruction(s) led to a transaction revert.

        Raises:
            AssertionError: When the trace or source can not be retrieved, the dev message cannot
            be found, or the found dev message does not match the expected dev message.
        """
        assertion_error_message = (
            self.dev_message.pattern
            if isinstance(self.dev_message, re.Pattern)
            else self.dev_message
        )
        assertion_error_prefix = f"Expected dev revert message '{assertion_error_message}'"
        dev_message, fail_msg = exception.dev_message
        if dev_message is None:
            msg = f"{assertion_error_prefix}: {fail_msg}" if fail_msg else assertion_error_prefix
            raise AssertionError(msg)

        message_matches = (
            (self.dev_message.match(dev_message) is not None)
            if isinstance(self.dev_message, re.Pattern)
            else (dev_message == self.dev_message)
        )
        if not message_matches:
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

        if self.expected_message is not None:
            self._check_expected_message(exc_value)

        # Returning True causes the expected exception not to get raised
        # and the test to pass
        return True
