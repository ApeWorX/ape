import pytest

from ape import __all__


# NOTE: We export `__all__` into the IPython session that the console runs in
@pytest.mark.parametrize("item", __all__)
def test_console(ape_cli, runner, item):
    result = runner.invoke_using_test_network(ape_cli, ["console"], input=f"{item}\nexit\n")
    assert result.exit_code == 0, result.output
