from ape.types import CallTreeNode
from ape.utils.trace import parse_rich_tree


def test_parse_rich_tree(vyper_contract_instance):
    """
    Show that when full selector is set as the method ID,
    the tree-output only shows the short method name.
    """
    contract_id = vyper_contract_instance.contract_type.name
    method_id = vyper_contract_instance.contract_type.methods["setAddress"].selector
    call = CallTreeNode(contract_id=contract_id, method_id=method_id)
    actual = parse_rich_tree(call).label
    expected = f"[#ff8c00]{contract_id}[/].[bright_green]setAddress[/]()"
    assert actual == expected
