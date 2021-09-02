_DEFAULT_NETWORKS_LIST = """
ecosystems:
    - ethereum  # Default
    - mainnet
    providers:
    - http  # Default
    - ropsten
    providers:
    - http  # Default
    - kovan
    providers:
    - http  # Default
    - rinkeby
    providers:
    - http  # Default
    - goerli
    providers:
    - http  # Default
    - development  # Default
    providers:
    - http  # Default
    - test
"""


def test_list(ape_cli, runner):
    result = runner.invoke(ape_cli, ["networks", "list"])
    expected = _DEFAULT_NETWORKS_LIST.strip()
    assert expected in result.output
