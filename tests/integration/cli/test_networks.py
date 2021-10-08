_DEFAULT_NETWORKS_LIST = """
ecosystems:
- name: ethereum
  isDefault: true
  networks:
  - name: mainnet
    providers:
    - name: http
      isDefault: true
  - name: ropsten
    providers:
    - name: http
      isDefault: true
  - name: kovan
    providers:
    - name: http
      isDefault: true
  - name: rinkeby
    providers:
    - name: http
      isDefault: true
  - name: goerli
    providers:
    - name: http
      isDefault: true
  - name: development
    isDefault: true
    providers:
    - name: http
      isDefault: true
    - name: test
"""


def test_list(ape_cli, runner):
    result = runner.invoke(ape_cli, ["networks", "list"])
    expected = _DEFAULT_NETWORKS_LIST.strip()
    assert expected in result.output
