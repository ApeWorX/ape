from ape_plugins.utils import FIRST_CLASS_PLUGINS, SECOND_CLASS_PLUGINS

INSTALLED_CORE_PLUGINS_HEADER = "Installed Core Plugins"
INSTALLED_PLUGINS_HEADER = "Installed Plugins"
AVAILABLE_PLUGINS_HEADER = "Available Plugins"


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

    headers = [INSTALLED_CORE_PLUGINS_HEADER, INSTALLED_PLUGINS_HEADER, AVAILABLE_PLUGINS_HEADER]
    headers = [h for h in headers if h in output]  # filter headers
    output_dict = {}
    output = output.split("\n\n")

    # splits dynamically into a dictionary of values for the output to be processed
    for index, value in enumerate(output):
        value = value.replace(headers[index] + ":\n", "")
        output_dict[headers[index]] = value
    """
    {
        Installed Core Plugins: 'Installed Core Plugins:\n  test\n  geth\n  accounts\n  ethereum\n
        compile\n  networks\n  console\n  pm\n  plugins\n  run',
        Available Plugins: 'Available Plugins:\n  tokens\n  trezor\n  debug\n  vyper\n  hardhat\n
        infura\n  etherscan\n  ledger\n  solidity\n  ens\n'}
        INSTALLED_CORE_PLUGINS_HEADER = "Installed Core Plugins"
    """
    for key, value in output_dict.items():
        section = key
        if expected_section == section:
            assert plugin in output_dict[key], "Not in the Section"
        else:
            assert plugin not in output_dict[key], "Wrong Section"

    #


# test plugins list -a with github access token and no 2nd class or third class installed
def test_plugins_list_all(ape_cli, runner):
    result = runner.invoke(ape_cli, ["plugins", "list", "-a"])
    assert result.exit_code == 0  # no errors when it runs

    assert_plugins_in_output(FIRST_CLASS_PLUGINS, result.output, INSTALLED_CORE_PLUGINS_HEADER)
    assert_plugins_in_output(SECOND_CLASS_PLUGINS, result.output, AVAILABLE_PLUGINS_HEADER)

    # all list available accessible only if you have github token
    # display everything as a plugins and as installed
    # with github token display availble
    # make a mock 3rd class plugins and live in the test directory
    # for testing purpose


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


def setup_plugins():
    # Set github token to test token
    #
    # user_token = environ['GITHUB_ACCESS_TOKEN']
    # environ['GITHUB_ACCESS_TOKEN'] = 'TEST'
    # plugins run a script to install plugins
    pass


def unintall_plugins():
    # runs script to uninstall plugins
    pass


def test_github_access_token(ape_cli, runner, caplog):
    pass
    # result = runner.invoke(ape_cli, ["plugins", "list"])
    # breakpoint()
    # assert result.exit_code == 0, "Exit was not successful"
    # assert "$GITHUB_ACCESS_TOKEN not set, skipping 2nd class plugins\n" in result.output

    # github token invoke with enviorment in click documenation test cli apps
    # isolate installed enviorment during testing
