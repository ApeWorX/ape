from ape.exceptions import ApeException


class MulticallException(ApeException):
    pass


class InvalidOption(MulticallException):
    def __init__(self, option_name: str):
        super().__init__(f"Option '{option_name}' not supported.")


class ValueRequired(MulticallException):
    def __init__(self, amount: int):
        super().__init__(f"This transaction must send at least '{amount / 1e18}' ether.")


class UnsupportedChainError(MulticallException):
    def __init__(self):
        super().__init__("Multicall not supported on this chain.")


class NotExecutedError(MulticallException):
    def __init__(self):
        super().__init__("Multicall not executed yet.")
