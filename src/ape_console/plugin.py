import click
from click.testing import CliRunner
from eth_utils import is_hex
from IPython import get_ipython  # type: ignore
from IPython.core.magic import Magics, line_magic, magics_class  # type: ignore

import ape
from ape._cli import cli
from ape.types import AddressType


@magics_class
class ApeConsoleMagics(Magics):
    @line_magic
    def ape(self, line: str = ""):
        """
        Run Ape CLI commands within an ``ape console`` session.

        Usage example::

            %ape accounts list

        """
        runner = CliRunner()
        result = runner.invoke(cli, line)
        click.echo(result.output)
        return result

    @line_magic
    def bal(self, line: str = ""):
        """
        Show an account balance in human-readable form.

        Usage example::

            account = accounts.load("me")
            %bal account
        """

        ipython = get_ipython()
        if not line:
            raise ValueError("Missing argument.")

        provider = ape.networks.provider
        ecosystem = provider.network.ecosystem
        result = eval(line, ipython.user_global_ns, ipython.user_ns)
        if isinstance(result, str) and not is_hex(result):
            # Check if is an account alias.
            address = ape.accounts.load(result).address
        else:
            address = ape.convert(result, AddressType)

        decimals = ecosystem.fee_token_decimals
        symbol = ecosystem.fee_token_symbol
        balance = provider.get_balance(address)
        return f"{round(balance / 10 ** decimals, 8)} {symbol}"


def load_ipython_extension(ipython):
    ipython.register_magics(ApeConsoleMagics)
