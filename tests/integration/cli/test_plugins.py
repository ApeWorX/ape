from os import environ

from ape_plugins.utils import FIRST_CLASS_PLUGINS, SECOND_CLASS_PLUGINS

# obtaining result limit assumption
# first class is filled in
# maybe it is not filled


# ape plugins test not required since it would be a click bug not us

# test plugins list with github access token and no 2nd class or third class installed
def test_plugins_list(ape_cli, runner):
    result = runner.invoke(ape_cli, ["plugins", "list"])
    print(result.output)
    assert result.exit_code == 0  # no errors when it runs
    assert "No plugins installed\n" == result.output


# test plugins list -a with github access token and no 2nd class or third class installed
def test_plugins_list_a(ape_cli, runner):
    result = runner.invoke(ape_cli, ["plugins", "list", "-a"])
    print(result.output)
    assert result.exit_code == 0  # no errors when it runs
    assert "Installed Core Plugins:" in result.output
    assert "Available Plugins" in result.output
    assert "Installed Plugins:" not in result.output
    # all(...)  # every single item in the iterator is "truthy" truthy not none and not false
    assert all(plugin in result.output for plugin in FIRST_CLASS_PLUGINS)
    assert all(plugin in result.output for plugin in SECOND_CLASS_PLUGINS)

    # path lib
    # strip ape_
    # save as first class plugins

    # 2nd class comes from github api, use import to get names

    # make a mock 3rd class plugins and live in the test directory
    # for testing purpose

    # FIRST CLASS
    # SECOND CLASS


"""
(apeworx) chris@DESKTOP-ID4V0R6:~/ape$ ape plugins list -a
Installed Core Plugins:
  test
  plugins
  run
  console
  compile
  accounts
  networks
  pm
  ethereum
  geth

Available Plugins:
  etherscan
  infura
  tokens
  ledger
  hardhat
  debug
  vyper
  ens
  trezor
  solidity
"""


def test_install_uninstall_plugins(ape_cli, runner):

    # ape plugins add vyper -y
    result = runner.invoke(ape_cli, ["plugins", "add", "vyper", "-y"])
    # result = runner.invoke(ape_cli, "plugins", "add", "jules", "-y")

    # breakpoint()
    assert result.exit_code == 0  # no errors when it runs
    assert "INFO: Installing ape_vyper...\n" in result.output

    """
(apeworx) chris@DESKTOP-ID4V0R6:~/ape$ ape plugins list
Installed Plugins:
  vyper     0.1.0a7
  jules      0.1.dev10+g0ca16f6)
    """

    # ape plugins list
    result = runner.invoke(ape_cli, ["plugins", "list"])
    assert result.exit_code == 0  # no errors when it runs
    assert "Installed Plugins:" in result.output

    # ape plugins list -a
    result = runner.invoke(ape_cli, ["plugins", "list", "-a"])
    assert result.exit_code == 0  # no errors when it runs
    assert "Installed Core Plugins:" in result.output
    assert "Installed Plugins:" in result.output
    assert "Available Plugins:" in result.output
    # second class
    # third class name

    # ape plugins remove vyper -y
    result = runner.invoke(ape_cli, ["plugins", "remove", "vyper", "-y"])

    # NOTHING NO RESPONSE

    result = runner.invoke(ape_cli, ["plugins", "list"])
    assert result.exit_code == 0  # no errors when it runs
    assert "No plugins installed" in result.output


def test_github_access_token(ape_cli, runner, monkeypatch):
    # read test token
    github_access_token = environ["TEST_GITHUB_ACCESS_TOKEN"]
    # set real token with test token
    monkeypatch.setenv("GITHUB_ACCESS_TOKEN", github_access_token, prepend=False)
    monkeypatch.delenv("GITHUB_ACCESS_TOKEN", raising=True)

    result = runner.invoke(ape_cli, ["plugins", "list"])
    breakpoint()
    assert result.exit_code == 0  # no errors when it runs

    # assert 'No plugins installed\n' == result.output
    # @TODO
    # 5 github token invoke with enviorment in click documenation test cli apps
    # isolate installed enviorment during testing
    # en
