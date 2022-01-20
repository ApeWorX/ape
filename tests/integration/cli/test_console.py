import pytest

from ape import __all__
from tests.integration.cli.utils import skip_projects


# NOTE: We export `__all__` into the IPython session that the console runs in
@skip_projects(["geth"])
@pytest.mark.parametrize("item", __all__)
def test_console(ape_cli, runner, item):
    result = runner.invoke(ape_cli, ["console"], input=f"{item}\nexit\n", catch_exceptions=False)
    assert result.exit_code == 0, result.output
    result = runner.invoke(
        ape_cli, ["console", "-v", "debug"], input=f"{item}\nexit\n", catch_exceptions=False
    )
    assert result.exit_code == 0, result.output
