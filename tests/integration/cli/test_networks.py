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
└── development  (default)
    ├── geth  (default)
    └── test
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
  - name: development
    isDefault: true
    providers:
    - name: geth
      isDefault: true
    - name: test
  - name: mainnet-fork
"""


def test_list(ape_cli, runner):
    result = runner.invoke(ape_cli, ["networks", "list"])
    expected = _DEFAULT_NETWORKS_TREE.strip()
    actual = result.output

    # The output from `rich` causes a bunch of extra spaces to
    # appear at the end of each line. For easier testing, we remove those here.
    lines = actual.split("\n")
    new_lines = []
    for line in lines:
        if line:
            new_lines.append(line.rstrip())

    actual = "\n".join(new_lines)
    assert actual == expected


def test_list_yaml(ape_cli, runner):
    result = runner.invoke(ape_cli, ["networks", "list", "--format", "yaml"])
    expected = _DEFAULT_NETWORKS_YAML.strip()
    assert expected in result.output
