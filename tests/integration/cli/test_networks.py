_DEFAULT_NETWORKS_LIST = """
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
"""


def test_list(ape_cli, runner):
    result = runner.invoke(ape_cli, ["networks", "list"])
    expected = _DEFAULT_NETWORKS_LIST.strip()
    assert expected in result.output
