import click

import ape

"""
Part of test that makes sure a contract is re-compiled
before running the script. The test changes a view method
and asserts the changed method's name appears in the script
output.
"""


def main():
    contract = ape.project.VyperContract
    for method in contract.contract_type.view_methods:
        click.echo(method.name)
