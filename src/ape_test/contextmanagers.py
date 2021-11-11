from typing import Optional, Type

from ape.exceptions import ContractLogicError


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
                f"Transaction did not revert.\nHowever, an exception occurred: {exc_value}"
            ) from exc_value

        actual = exc_value.revert_message

        if self.expected_message is not None and self.expected_message != actual:
            raise AssertionError(
                f"Expected revert message '{self.expected_message}' but got '{actual}'."
            )

        # Returning True causes the expected exception not to get raised
        # and the test to pass
        return True
