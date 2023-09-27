import shlex

import click
from click.testing import CliRunner
from eth_utils import is_hex
from IPython import get_ipython
from IPython.core.magic import Magics, line_magic, magics_class

import ape
from ape._cli import cli
from ape.exceptions import Abort, ApeException, handle_ape_exception
from ape.logging import logger
from ape.types import AddressType
from ape.utils import cached_property


@magics_class
class ApeConsoleMagics(Magics):
    @cached_property
    def ipython(self):
        if ipython := get_ipython():
            return ipython

        raise ValueError("Must be called from an IPython session.")

    @line_magic
    def ape(self, line: str = ""):
        """
        Run Ape CLI commands within an ``ape console`` session.

        Usage example::

            %ape accounts list

        """
        runner = CliRunner()
        if "console" in [x.strip("\"' \t\n") for x in shlex.split(line)]:
            # Prevent running console within console because usually bad
            # stuff happens when you try to do this.
            raise ValueError("Unable to run `console` within a console.")

        result = runner.invoke(cli, line)
        if result.output:
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

        if not line:
            raise ValueError("Missing argument.")

        provider = ape.networks.provider
        ecosystem = provider.network.ecosystem
        result = eval(line, self.ipython.user_global_ns, self.ipython.user_ns)
        if isinstance(result, str) and not is_hex(result):
            # Check if is an account alias.
            address = ape.accounts.load(result).address
        else:
            address = ape.convert(result, AddressType)

        decimals = ecosystem.fee_token_decimals
        symbol = ecosystem.fee_token_symbol
        balance = provider.get_balance(address)
        return f"{round(balance / 10 ** decimals, 8)} {symbol}"


def custom_exception_handler(self, etype, value, tb, tb_offset=None):
    if not handle_ape_exception(value, [self.user_ns["project"].path]):
        logger.error(Abort.from_ape_exception(value).format_message())


def load_ipython_extension(ipython):
    ipython.register_magics(ApeConsoleMagics)
    ipython.set_custom_exc((ApeException,), custom_exception_handler)
