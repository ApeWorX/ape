import re
from os import environ

from ape_plugins.utils import FIRST_CLASS_PLUGINS, SECOND_CLASS_PLUGINS

INSTALLED_CORE_PLUGINS_HEADER = "Installed Core Plugins"
INSTALLED_PLUGINS_HEADER = "Installed Plugins"
AVAILABLE_PLUGINS_HEADER = "Available Plugins"
# obtaining result limit assumption
# first class is filled in
# maybe it is not filled


# ape plugins test not required since it would be a click bug not us

# test plugins list with github access token and no 2nd class or third class installed
def test_plugins_list_nothing_installed(ape_cli, runner):
    result = runner.invoke(ape_cli, ["plugins", "list"])
    assert result.exit_code == 0, result.output  # no errors when it runs
    assert "No plugins installed\n" == result.output


def assert_plugins_in_output(plugins, output, header):
    expected_plugins = [p.replace("ape_", "") for p in plugins if p != "ape"]
    for plugin in expected_plugins:
        assert_in_section(plugin, output, header)


def assert_in_section(plugin, output, expected_section):
    in_section = False
    headers = [INSTALLED_CORE_PLUGINS_HEADER, INSTALLED_PLUGINS_HEADER, AVAILABLE_PLUGINS_HEADER]
    last_index = len(headers)
    for i in range(0, last_index):
        section = headers[i]
        if expected_section == section:
            output_parts = output.split(expected_section)
            assert len(output_parts) == 2, f"Section '{expected_section}' not in output"
            assert plugin in output_parts[1]  # It should come after section

            if i < last_index:
                # Verify that the plugin is not actually in the next section
                next_section_header = headers[i + 1]
                next_section_parts = output.split(next_section_header)

                if len(next_section_parts) == 2:
                    next_section = next_section_parts[-1]
                    assert plugin not in next_section

                in_section = True
    assert in_section, "Did not find plugin in section"


# test plugins list -a with github access token and no 2nd class or third class installed
def test_plugins_list_all(ape_cli, runner):
    result = runner.invoke(ape_cli, ["plugins", "list", "-a"])
    assert result.exit_code == 0  # no errors when it runs
    # breakpoint()

    # re.search vs re.match
    assert re.search(r"Installed Core Plugins:\n", result.output)
    # assert re.search(r"Installed Plugins\n",result.output)
    assert re.search(r"Available Plugins:\n", result.output)
    # change re.search to in result.output

    # list comprehension
    assert_plugins_in_output(FIRST_CLASS_PLUGINS, result.output, INSTALLED_CORE_PLUGINS_HEADER)

    # Assume that all second class is not installed and avialable
    assert_plugins_in_output(SECOND_CLASS_PLUGINS, result.output, AVAILABLE_PLUGINS_HEADER)

    # assert_plugins_in_output

    # expected_second_class_plugins = []

    # all(...)  # every single item in the iterator is "truthy" truthy not none and not false
    # assert all(plugin in result.output for plugin in FIRST_CLASS_PLUGINS)

    # all list available accessible only if you have github token
    # display everything as a plugins and as installed
    # with github token display availble

    # -a will display core

    # assert all(plugin in result.output for plugin in SECOND_CLASS_PLUGINS)

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
