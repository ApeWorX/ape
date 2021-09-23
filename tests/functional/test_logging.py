import click
import pytest
from click.testing import CliRunner

from ape.options import plugin_helper


@pytest.fixture
def simple_runner():
    return CliRunner()


@click.group()
def group_for_testing():
    pass


def test_info(simple_runner):
    @group_for_testing.command()
    @plugin_helper()
    def cmd(helper):
        helper.log_info("this is a test")

    result = simple_runner.invoke(group_for_testing, ["cmd"])
    assert "INFO" in result.output
    assert "this is a test" in result.output


def test_warning(simple_runner):
    @group_for_testing.command()
    @plugin_helper()
    def cmd(helper):
        helper.log_warning("this is a test")

    result = simple_runner.invoke(group_for_testing, ["cmd"])
    assert "WARNING" in result.output
    assert "this is a test" in result.output


def test_success(simple_runner):
    @group_for_testing.command()
    @plugin_helper()
    def cmd(helper):
        helper.log_success("this is a test")

    result = simple_runner.invoke(group_for_testing, ["cmd"])
    assert "SUCCESS" in result.output
    assert "this is a test" in result.output
