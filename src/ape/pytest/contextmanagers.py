import re
from collections import deque
from typing import Optional, Type, Union

import ape
from ape.exceptions import (
    APINotImplementedError,
    ContractLogicError,
    ProviderError,
    SignatureError,
    TransactionError,
)


class RevertsContextManager:
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
        txn = exception.txn

        if txn is None or txn.receiver is None:
            raise AssertionError("Could not fetch transaction information to check dev message.")

        try:
            contract = ape.Contract(txn.receiver)
        except ValueError as exc:
            raise AssertionError(
                f"Could not fetch contract at {txn.receiver} to check dev message."
            ) from exc

        if contract.contract_type.pcmap is None:
            raise AssertionError("Compiler does not support source code mapping.")

        try:
            txn_hash = txn.txn_hash.hex()
        except SignatureError as exc:
            raise AssertionError(
                "Cannot check dev message; "
                "transaction failed before signing, "
                "likely during gas estimation."
            ) from exc

        try:
            trace = deque(txn.provider.get_transaction_trace(txn_hash=txn_hash))
        except APINotImplementedError as exc:
            raise AssertionError(
                "Cannot check dev message; provider must support transaction tracing."
            ) from exc
        except ProviderError as exc:
            raise AssertionError("Cannot fetch transaction trace.") from exc

        pc = None
        pcmap = contract.contract_type.pcmap.parse()

        # To find a suitable line for inspecting dev messages, we must start at the revert and work
        # our way backwards. If the last frame's PC is in the PC map, the offending line is very
        # likely a 'raise' statement.
        if trace[-1].pc in pcmap:
            pc = trace[-1].pc

        # Otherwise we must traverse the trace backwards until we find our first suitable candidate.
        else:
            while len(trace) > 0:
                frame = trace.pop()
                if frame.pc in pcmap:
                    pc = frame.pc
                    break

        # We were unable to find a suitable PC that matched the compiler's map.
        if pc is None:
            raise AssertionError("Could not find line that caused revert.")

        offending_source = pcmap[pc]

        # The compiler PC map had PC information, but not source information.
        if offending_source is None or offending_source.line_start is None:
            raise AssertionError("Could not find line that caused revert.")

        assertion_error_message = (
            self.dev_message.pattern
            if isinstance(self.dev_message, re.Pattern)
            else self.dev_message
        )

        assertion_error_prefix = f"Expected dev revert message '{assertion_error_message}'"

        dev_messages = contract.contract_type.dev_messages or {}

        if offending_source.line_start not in dev_messages:
            raise AssertionError(f"{assertion_error_prefix} but there was none.")

        contract_dev_message = dev_messages[offending_source.line_start]

        message_matches = (
            (self.dev_message.match(contract_dev_message) is not None)
            if isinstance(self.dev_message, re.Pattern)
            else (contract_dev_message == self.dev_message)
        )

        if not message_matches:
            raise AssertionError(f"{assertion_error_prefix} but got '{contract_dev_message}'.")

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
