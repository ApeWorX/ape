from ape.api.config import PluginConfig


class AccountsConfig(PluginConfig):
    """
    Config accounts generally.
    """

    show_full_calldata: bool = False
    """
    When signing transactions, ``True`` will always show the full
    calldata where ``False`` shows an abridged version of the data
    (enough to see the method ID). Defaults to ``False``.
    """
