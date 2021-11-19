from typing import Optional


class ApeException(Exception):
    """
    An exception raised by ape.
    """

    def __init__(self, message):
        if not message.endswith("."):
            message = f"{message}."
        super().__init__(message)


class AccountsError(ApeException):
    """
    Raised when a problem occurs when using accounts.
    """


class AliasAlreadyInUseError(AccountsError):
    """
    Raised when attempting to add an account using an alias
    that already maps to another account.
    """

    def __init__(self, alias: str):
        self.alias = alias
        super().__init__(f"Account with alias '{alias}' already in use.")


class SignatureError(AccountsError):
    """
    Raised when there are issues with signing.
    """


class ContractError(ApeException):
    """
    Raised when issues occur when interacting with a contract
    (calls or transactions).
    """


class ArgumentsLengthError(ContractError):
    """
    Raised when calling a contract method with the wrong number of arguments.
    """

    def __init__(self):
        message = "The number of the given arguments do not match what is defined in the ABI."
        super().__init__(message)


class DecodingError(ContractError):
    """
    Raised when issues occur while decoding data from
    a contract call or transaction.
    """

    def __init__(self):
        super().__init__("Output corrupted.")


class TransactionError(ContractError):
    """
    Raised when issues occur related to transactions.
    """

    DEFAULT_MESSAGE = "Tranaction failed."

    def __init__(
        self,
        base_err: Optional[Exception] = None,
        message: Optional[str] = None,
        code: Optional[int] = None,
    ):
        self.base_err = base_err
        if not message:
            message = str(base_err) if base_err else self.DEFAULT_MESSAGE

        self.message = message
        self.code = code

        ex_message = f"({code}) {message}" if code else message
        super().__init__(ex_message)


class VirtualMachineError(TransactionError):
    """
    Raised when a transaction error occurs in a virtual machine.
    """


class ContractLogicError(VirtualMachineError):
    """
    Raised when there is a contract-defined revert,
    such as from an assert/require statement.
    """

    def __init__(self, revert_message: Optional[str] = None):
        super().__init__(message=revert_message)

    @property
    def revert_message(self):
        return self.message

    @classmethod
    def from_error(cls, err: Exception):
        """
        Creates this class from the error message of the given
        error.

        This should be overridden whenever possible to handle
        provider-specific use-cases for raising this error.
        """
        return cls(str(err))


class OutOfGasError(TransactionError):
    """
    Raised when detecting a transaction failed because it ran
    out of gas.
    """

    def __init__(self, code: Optional[int] = None):
        super().__init__(message="The transaction ran out of gas.", code=code)


class ContractDeployError(TransactionError):
    """
    Raised when a problem occurs when deploying a contract.
    """


class NetworkError(ApeException):
    """
    Raised when a problem occurs when using blockchain networks.
    """


class NetworkNotFoundError(NetworkError):
    """
    Raised when the network with the given name was not found.
    """

    def __init__(self, network: str):
        self.network = network
        message = f"No network named '{network}'."
        super().__init__(message)


class CompilerError(ApeException):
    """
    Raised when unable to compile.
    """


class ProjectError(ApeException):
    """
    Raised when problems occur in a project.
    """


class ConversionError(ApeException):
    """
    Raised when unable to convert a value.
    """


class ProviderError(ApeException):
    """
    Raised when a problem occurs when using providers.
    """


class ConfigError(ApeException):
    """
    Raised when a problem occurs from the configuration file.
    """


class AddressError(ApeException):
    """
    Raised when a problem occurs regarding an address.
    """
