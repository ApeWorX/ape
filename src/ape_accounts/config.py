from ape.api.config import PluginConfig
from ape.utils.abi import CalldataRepr


class AccountsConfig(PluginConfig):
    """
    Config accounts generally.
    """

    calldata_repr: CalldataRepr = CalldataRepr.abridged
    """
    When signing transactions, ``full`` will always show the full
    calldata where ``abridged`` shows an abridged version of the data
    (enough to see the method ID). Defaults to ``abridged``.
    """
