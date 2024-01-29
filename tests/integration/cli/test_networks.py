from ape.api.networks import LOCAL_NETWORK_NAME
from tests.conftest import GETH_URI, geth_process_test

from .utils import run_once, skip_projects_except

_DEFAULT_NETWORKS_TREE = """
ethereum  (default)
├── goerli
│   └── geth  (default)
├── local  (default)
│   ├── geth
│   └── test  (default)
├── mainnet
│   └── test  (default)
└── sepolia
    └── geth  (default)
"""
_DEFAULT_NETWORKS_YAML = """
ecosystems:
- isDefault: true
  name: ethereum
  networks:
  - name: goerli
    providers:
    - isDefault: true
      name: geth
  - name: goerli-fork
    providers: []
  - isDefault: true
    name: local
    providers:
    - name: geth
    - isDefault: true
      name: test
  - name: mainnet
    providers:
    - isDefault: true
      name: geth
  - name: mainnet-fork
    providers: []
  - name: sepolia
    providers:
    - isDefault: true
      name: geth
  - name: sepolia-fork
    providers: []
"""
_GETH_NETWORKS_TREE = """
ethereum  (default)
├── goerli
│   └── geth  (default)
├── local  (default)
│   └── geth  (default)
└── mainnet
    └── geth  (default)
"""
_TEST_PROVIDER_TREE_OUTPUT = """
ethereum  (default)
└── local  (default)
    └── test  (default)
"""
_GOERLI_NETWORK_TREE_OUTPUT = """
ethereum  (default)
└── goerli
    └── geth  (default)
"""
_CUSTOM_NETWORKS_TREE = """
ethereum  (default)
├── apenet
│   └── geth  (default)
├── apenet1
│   └── geth  (default)
├── goerli
│   └── geth  (default)
├── local  (default)
│   └── geth  (default)
└── mainnet
    └── geth  (default)
"""


def assert_rich_text(actual: str, expected: str):
    """
    The output from `rich` causes a bunch of extra spaces to
    appear at the end of each line. For easier testing, we remove those here.
    Also, we ignore whether the expected line is at the end or in the middle
    of the output to handle cases when the test-runner has additional plugins
    installed.
    """
    expected_lines = [
        x.replace("└", "").replace("├", "").replace("│", "").strip()
        for x in expected.strip().split("\n")
    ]
    actual_lines = [
        x.replace("└", "").replace("├", "").replace("│", "").strip()
        for x in actual.strip().split("\n")
    ]

    for expected_line in expected_lines:
        assert expected_line in actual_lines


@run_once
def test_list(ape_cli, runner):
    result = runner.invoke(ape_cli, ["networks", "list"])

    # Grab ethereum
    actual = "ethereum  (default)\n" + "".join(result.output.split("ethereum  (default)\n")[-1])

    assert_rich_text(actual, _DEFAULT_NETWORKS_TREE)


@run_once
def test_list_yaml(ape_cli, runner):
    result = runner.invoke(
        ape_cli, ["networks", "list", "--format", "yaml"], catch_exceptions=False
    )
    expected_lines = _DEFAULT_NETWORKS_YAML.strip().split("\n")

    for expected_line in expected_lines:
        if expected_line.lstrip() == "providers: []":
            # Skip these lines in case test-runner has installed providers
            continue

        if (
            expected_line.lstrip().startswith("- name:")
            and expected_line not in result.output
            and "explorer:" in result.output
        ):
            # May have explorers installed - ignore that.
            expected_line = expected_line.lstrip(" -")

        assert expected_line in result.output, result.output


@skip_projects_except("geth")
def test_list_geth(ape_cli, runner, networks, project):
    result = runner.invoke(ape_cli, ["networks", "list"])

    # Grab ethereum
    actual = "ethereum  (default)\n" + "".join(result.output.split("ethereum  (default)\n")[-1])

    assert_rich_text(actual, _GETH_NETWORKS_TREE)

    # Assert that URI still exists for local network
    # (was bug where one network's URI disappeared when setting different network's URI)
    geth_provider = networks.get_provider_from_choice(f"ethereum:{LOCAL_NETWORK_NAME}:geth")
    actual_uri = geth_provider.uri
    assert actual_uri == GETH_URI


@run_once
def test_list_filter_networks(ape_cli, runner, networks):
    result = runner.invoke(ape_cli, ["networks", "list", "--network", "goerli"])

    # Grab ethereum
    actual = "ethereum  (default)\n" + "".join(result.output.split("ethereum  (default)\n")[-1])

    assert_rich_text(actual, _GOERLI_NETWORK_TREE_OUTPUT)


@run_once
def test_list_filter_providers(ape_cli, runner, networks):
    result = runner.invoke(ape_cli, ["networks", "list", "--provider", "test"])

    # Grab ethereum
    actual = "ethereum  (default)\n" + "".join(result.output.split("ethereum  (default)\n")[-1])

    assert_rich_text(actual, _TEST_PROVIDER_TREE_OUTPUT)


@skip_projects_except("geth")
def test_list_custom_networks(ape_cli, runner):
    result = runner.invoke(ape_cli, ["networks", "list"])
    actual = "ethereum  (default)\n" + "".join(result.output.split("ethereum  (default)\n")[-1])
    assert_rich_text(actual, _CUSTOM_NETWORKS_TREE)


@run_once
def test_run_not_subprocess_provider(ape_cli, runner):
    cmd = ("networks", "run", "--network", "ethereum:local:test")
    result = runner.invoke(ape_cli, cmd)
    assert result.exit_code != 0
    assert (
        result.output
        == "ERROR: `ape networks run` requires a provider that manages a process, not 'test'.\n"
    )


@run_once
def test_run_custom_network(ape_cli, runner):
    cmd = ("networks", "run", "--network", "ethereum:local:test")
    result = runner.invoke(ape_cli, cmd)
    assert result.exit_code != 0
    assert (
        result.output
        == "ERROR: `ape networks run` requires a provider that manages a process, not 'test'.\n"
    )


@geth_process_test
@skip_projects_except("geth")
def test_run_already_running(ape_cli, runner, geth_provider):
    cmd = ("networks", "run", "--network", f"ethereum:{LOCAL_NETWORK_NAME}:geth")
    result = runner.invoke(ape_cli, cmd)
    assert result.exit_code != 0
    assert "ERROR: Process already running." in result.output
