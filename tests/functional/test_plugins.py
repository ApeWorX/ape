import pytest

from ape.plugins import _get_name_from_install

EXPECTED_PLUGIN_NAME = "plugin_name"


@pytest.mark.parametrize(
    "name",
    (
        f"{EXPECTED_PLUGIN_NAME}_0_4_1_dev1_g048574f",
        f"{EXPECTED_PLUGIN_NAME}_0_4_1_dev1_g791b83a_d20220817",
        f"{EXPECTED_PLUGIN_NAME}_0_4_0",
    ),
)
def test_get_name_from_install_editable_examples(name):
    editable_name = f"__editable___ape_{name}_finder"
    actual = _get_name_from_install(editable_name)
    assert actual == f"ape_{EXPECTED_PLUGIN_NAME}"
