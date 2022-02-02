from .utils import skip_projects, skip_projects_except

_DEFAULT_NETWORKS_TREE = """
ethereum  (default)
├── mainnet
│   └── geth  (default)
├── ropsten
│   └── geth  (default)
├── kovan
│   └── geth  (default)
├── rinkeby
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
  - name: ropsten
    providers:
    - name: geth
      isDefault: true
  - name: kovan
    providers:
    - name: geth
      isDefault: true
  - name: rinkeby
    providers:
    - name: geth
      isDefault: true
  - name: goerli
    providers:
    - name: geth
      isDefault: true
  - name: local
    isDefault: true
    providers:
    - name: geth
    - name: test
      isDefault: true
  - name: mainnet-fork
    providers: []
"""
_GETH_NETWORKS_YAML = """
ethereum  (default)
├── mainnet
│   └── geth  (default)
├── ropsten
│   └── geth  (default)
├── kovan
│   └── geth  (default)
├── rinkeby
│   └── geth  (default)
├── goerli
│   └── geth  (default)
└── local  (default)
    ├── geth  (default)
    └── test
"""


def assert_rich_text(actual: str, expected: str):
    """
    The output from `rich` causes a bunch of extra spaces to
    appear at the end of each line. For easier testing, we remove those here.
    """
    expected = expected.strip()
    lines = actual.split("\n")
    new_lines = []
    for line in lines:
        if line:
            new_lines.append(line.rstrip())

    actual = "\n".join(new_lines)
    assert actual == expected


@skip_projects(["geth"])
def test_list(ape_cli, runner):
    result = runner.invoke(ape_cli, ["networks", "list"])
    assert_rich_text(result.output, _DEFAULT_NETWORKS_TREE)


@skip_projects(["geth"])
def test_list_yaml(ape_cli, runner):
    result = runner.invoke(ape_cli, ["networks", "list", "--format", "yaml"])
    expected = _DEFAULT_NETWORKS_YAML.strip()
    assert expected in result.output, result.output


@skip_projects_except(["geth"])
def test_change_default_from_config_file(ape_cli, runner):
    result = runner.invoke(ape_cli, ["networks", "list"])
    assert_rich_text(result.output, _GETH_NETWORKS_YAML)
