from ape.api.networks import LOCAL_NETWORK_NAME
from tests.conftest import GETH_URI

from .utils import run_once, skip_projects_except

_DEFAULT_NETWORKS_TREE = """
ethereum  (default)
├── mainnet
│   └── geth  (default)
├── goerli
│   └── geth  (default)
└── local  (default)
    ├── geth
    └── test  (default)
"""
_DEFAULT_NETWORKS_YAML = """
ecosystems:
- name: ethereum
  isDefault: true
  networks:
  - name: mainnet
    providers:
    - name: geth
      isDefault: true
  - name: mainnet-fork
    providers: []
  - name: goerli
    providers:
    - name: geth
      isDefault: true
  - name: goerli-fork
    providers: []
  - name: local
    isDefault: true
    providers:
    - name: geth
    - name: test
      isDefault: true
"""
_GETH_NETWORKS_TREE = """
ethereum  (default)
├── mainnet
│   └── geth  (default)
├── goerli
│   └── geth  (default)
└── local  (default)
    ├── geth  (default)
    └── test
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
    assert_rich_text(result.output, _DEFAULT_NETWORKS_TREE)


@run_once
def test_list_yaml(ape_cli, runner):
    result = runner.invoke(ape_cli, ["networks", "list", "--format", "yaml"])
    expected_lines = _DEFAULT_NETWORKS_YAML.strip().split("\n")

    for expected_line in expected_lines:
        if expected_line.lstrip() == "providers: []":
            # Skip these lines in case test-runner has installed providers
            continue

        assert expected_line in result.output


@skip_projects_except("geth")
def test_geth(ape_cli, runner, networks):
    result = runner.invoke(ape_cli, ["networks", "list"])
    assert_rich_text(result.output, _GETH_NETWORKS_TREE)

    # Assert that URI still exists for local network
    # (was bug where one network's URI disappeared when setting different network's URI)
    geth_provider = networks.get_provider_from_choice(f"ethereum:{LOCAL_NETWORK_NAME}:geth")
    actual = geth_provider.uri
    assert actual == GETH_URI


@run_once
def test_filter_networks(ape_cli, runner, networks):
    result = runner.invoke(ape_cli, ["networks", "list", "--network", "goerli"])
    assert_rich_text(result.output, _GOERLI_NETWORK_TREE_OUTPUT)


@run_once
def test_filter_providers(ape_cli, runner, networks):
    result = runner.invoke(ape_cli, ["networks", "list", "--provider", "test"])
    assert_rich_text(result.output, _TEST_PROVIDER_TREE_OUTPUT)
