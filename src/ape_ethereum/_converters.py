from decimal import Decimal

from ape.api import ConverterAPI

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


class WeiConversions(ConverterAPI):
    """Converts units like `1 ether` to 1e18 wei"""

    def is_convertible(self, value: str) -> bool:
        if not isinstance(value, str):
            return False

        if " " not in value or len(value.split(" ")) > 2:
            return False

        _, unit = value.split(" ")

        return unit.lower() in ETHER_UNITS

    def convert(self, value: str) -> int:
        value, unit = value.split(" ")

        return int(Decimal(value) * ETHER_UNITS[unit.lower()])
