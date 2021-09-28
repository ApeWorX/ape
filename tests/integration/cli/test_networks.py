_DEFAULT_NETWORKS_LIST = """
ecosystems:
- name: ethereum  # Default
  - name: mainnet
    providers:
    - http  # Default
  - name: ropsten
    providers:
    - http  # Default
  - name: kovan
    providers:
    - http  # Default
  - name: rinkeby
    providers:
    - http  # Default
  - name: goerli
    providers:
    - http  # Default
  - name: development  # Default
    providers:
    - http  # Default
    - test
"""


def test_list(ape_cli, runner):
    result = runner.invoke(ape_cli, ["networks", "list"])
    expected = _DEFAULT_NETWORKS_LIST.strip()
    assert expected in result.output
