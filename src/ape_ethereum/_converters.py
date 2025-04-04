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
    """Converts units like `1 ether` to 1e18 wei."""

    def is_convertible(self, value: str) -> bool:
        if not isinstance(value, str):
            return False

        elif " " not in value or len(value.split(" ")) > 2:
            return False

        val, unit = value.split(" ")
        return unit.lower() in ETHER_UNITS and bool(NUMBER_PATTERN.match(val))

    def convert(self, value: str) -> int:
        value, unit = value.split(" ")
        converted_value = int(
            Decimal(value.replace("_", "").replace(",", "")) * ETHER_UNITS[unit.lower()]
        )
        return CurrencyValue(converted_value)


class WeiIntStrConversions(ConverterAPI):
    """Converts a int to a string units like 1e18 to '1 ether'."""

    def is_convertible(self, value: str) -> bool:
        return isinstance(value, int)

    def convert(self, value: int) -> str:
        from ape import convert

        decimal_value = convert(value, Decimal)

        return convert(decimal_value, str)


class EthDecimalStrConversions(ConverterAPI):
    """Converts a decimal to a string units like 1.0 to '1 ether'."""

    def is_convertible(self, value: str) -> bool:
        return isinstance(value, Decimal)

    def convert(self, value: Decimal) -> str:
        ETH_THRESHOLD = 1 / Decimal(1e3)
        GWEI_THRESHOLD = 1 / Decimal(1e12)

        if value < GWEI_THRESHOLD:
            return f"{value * Decimal(1e18).normalize():,f} wei"
        elif GWEI_THRESHOLD <= value < ETH_THRESHOLD:
            return f"{value * Decimal(1e9).normalize():,f} gwei"
        # value >= ETH_THRESHOLD
        return f"{value.normalize():,f} ether"


class WeiIntEthDecimalConversions(ConverterAPI):
    """Converts a int to a decimal units like 1e18 to Decimal('1.0')"""

    def is_convertible(self, value: int) -> bool:
        return isinstance(value, int)

    def convert(self, value: int) -> Decimal:
        return Decimal(value) / Decimal(1e18)
