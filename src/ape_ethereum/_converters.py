import re
from decimal import Decimal

from ape.api.convert import ConverterAPI
from ape.types.units import CurrencyValue

ETHER_UNITS = {
    "eth": int(1e18),
    "ether": int(1e18),
    "milliether": int(1e15),
    "finney": int(1e15),
    "microether": int(1e12),
    "szabo": int(1e12),
    "gwei": int(1e9),
    "shannon": int(1e9),
    "mwei": int(1e6),
    "lovelace": int(1e6),
    "kwei": int(1e3),
    "babbage": int(1e3),
    "wei": 1,
}
NUMBER_PATTERN = re.compile(r"^-?\d{1,3}(?:[,_]?\d{3})*(?:\.\d+)?(?:[eE][+-]?\d+)?$")


class WeiConversions(ConverterAPI):
    """Converts units like `1 ether` to 1e18 wei"""

    def is_convertible(self, value: str) -> bool:
        if not isinstance(value, str):
            return False

        if " " not in value or len(value.split(" ")) > 2:
            return False

        val, unit = value.split(" ")
        return unit.lower() in ETHER_UNITS and bool(NUMBER_PATTERN.match(val))

    def convert(self, value: str) -> int:
        value, unit = value.split(" ")
        converted_value = int(
            Decimal(value.replace("_", "").replace(",", "")) * ETHER_UNITS[unit.lower()]
        )
        return CurrencyValue(converted_value)
