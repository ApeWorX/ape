from typing import Any

import pytest
from eth_typing import ChecksumAddress

from ape.api import ConverterAPI
from ape.exceptions import ConversionError
from ape.managers.converters import ConversionManager
from ape.managers.plugins import PluginManager
from ape.types.address import AddressType


def test_convert_logs_and_passes_errors_from_is_convertible(conversion_manager, ape_caplog):
    """
    When checking if something is convertible, and is_convertible errors
    for whatever reason, log the error and consider it "not convertible".
    More than likely, it isn't by that converter and is a plugin-error.
    """
    error_msg = "Unexpected error!"

    class ProblematicConverter(ConverterAPI):
        def is_convertible(self, value: Any) -> bool:
            raise ValueError(error_msg)

        def convert(self, value: Any) -> Any:
            return value

    conversion_manager._converters[dict] = (ProblematicConverter(),)
    expected = f"Issue while checking `ProblematicConverter.is_convertible()`: {error_msg}"
    with pytest.raises(ConversionError):
        _ = conversion_manager.convert(123, dict)

    assert expected in ape_caplog.head


def test_plugin_converters_after_checksum_address_converter(mocker):
    """
    A plugin converter registered for ``ChecksumAddress`` should not
    stop the plugin converters after it from loading.
    """

    class MyAddressConverter(ConverterAPI):
        def is_convertible(self, value: Any) -> bool:
            return False

        def convert(self, value: Any) -> Any:
            return value

    class MyIntConverter(ConverterAPI):
        def is_convertible(self, value: Any) -> bool:
            return False

        def convert(self, value: Any) -> Any:
            return value

    plugin_converters = [
        ("my_address_plugin", (ChecksumAddress, MyAddressConverter)),
        ("my_int_plugin", (int, MyIntConverter)),
    ]
    mocker.patch.object(PluginManager, "converters", plugin_converters, create=True)
    converters = ConversionManager()._converters

    assert any(isinstance(c, MyAddressConverter) for c in converters[AddressType])
    assert any(isinstance(c, MyIntConverter) for c in converters[int])
