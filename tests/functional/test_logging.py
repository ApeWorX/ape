import click
import pytest
from click.testing import CliRunner

from ape.cli import ape_cli_context


@pytest.fixture
def simple_runner():
    return CliRunner()


@click.group()
def group_for_testing():
    pass


def test_info(simple_runner):
    @group_for_testing.command()
    @ape_cli_context()
    def cmd(cli_ctx):
        cli_ctx.logger.info("this is a test")

    result = simple_runner.invoke(group_for_testing, ["cmd"])
    assert "INFO" in result.output
    assert "this is a test" in result.output


def test_info_level_higher(simple_runner):
    @group_for_testing.command()
    @ape_cli_context()
    def cmd(cli_ctx):
        cli_ctx.logger.info("this is a test")

    result = simple_runner.invoke(group_for_testing, ["cmd", "-v", "WARNING"])

    # You don't get INFO log when log level is higher
    assert "INFO" not in result.output
    assert "this is a test" not in result.output


def test_warning(simple_runner):
    @group_for_testing.command()
    @ape_cli_context()
    def cmd(cli_ctx):
        cli_ctx.logger.warning("this is a test")

    result = simple_runner.invoke(group_for_testing, ["cmd"])
    assert "WARNING" in result.output
    assert "this is a test" in result.output


def test_warning_level_higher(simple_runner):
    @group_for_testing.command()
    @ape_cli_context()
    def cmd(cli_ctx):
        cli_ctx.logger.warning("this is a test")

    result = simple_runner.invoke(group_for_testing, ["cmd", "-v", "ERROR"])
    assert "WARNING" not in result.output
    assert "this is a test" not in result.output


def test_success(simple_runner):
    # Since the log level defaults to INFO,
    # this test also ensures that we get SUCCESS logs
    # without having to specify verbosity
    @group_for_testing.command()
    @ape_cli_context()
    def cmd(cli_ctx):
        cli_ctx.logger.success("this is a test")

    result = simple_runner.invoke(group_for_testing, ["cmd"])
    assert "SUCCESS" in result.output
    assert "this is a test" in result.output


def test_success_level_higher(simple_runner):
    @group_for_testing.command()
    @ape_cli_context()
    def cmd(cli_ctx):
        cli_ctx.logger.success("this is a test")

    result = simple_runner.invoke(group_for_testing, ["cmd", "-v", "WARNING"])
    assert "SUCCESS" not in result.output
    assert "this is a test" not in result.output
