from typing import Optional, Type

from ape.exceptions import ContractLogicError, TransactionError


class RevertsContextManager:
    def __init__(self, expected_message: Optional[str] = None):
        self.expected_message = expected_message

    def __enter__(self):
        pass

    def __exit__(self, exc_type: Type, exc_value: Exception, traceback) -> bool:
        if exc_type is None:
            raise AssertionError("Transaction did not revert.")

        if not isinstance(exc_value, ContractLogicError):
            raise AssertionError(
                f"Transaction did not revert.\n"
                f"However, an exception of type {type(exc_value)} occurred: {exc_value}"
            ) from exc_value

        actual = exc_value.revert_message

        # Validate the expected revert message if given one.
        if self.expected_message is not None and self.expected_message != actual:
            assertion_error_prefix = f"Expected revert message '{self.expected_message}'"

            if actual == TransactionError.DEFAULT_MESSAGE:
                # The transaction failed without a revert message
                # but the user is expecting one.
                raise AssertionError(f"{assertion_error_prefix} but there was none.")

            raise AssertionError(f"{assertion_error_prefix} but got '{actual}'.")

        # Returning True causes the expected exception not to get raised
        # and the test to pass
        return True
