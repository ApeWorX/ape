from typing import Any

import pytest

from ape.api import ConverterAPI
from ape.exceptions import ConversionError


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
