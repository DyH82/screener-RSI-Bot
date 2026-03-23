__all__ = ["ScreenerType", "TradebotType", "SignalSide"]

from enum import StrEnum
from enum import Enum

class ScreenerType(StrEnum):
    """Перечисление типов скринеров."""

    RSI = "RSI"
    """Скринер, который генерирует сигналы в соответствии с индикатором RSI."""

    EMA = "EMA"
    """Скринер, который генерирует сигналы в соответствии с индикатором EMA."""


class TradebotType(StrEnum):
    """Перечисление типов торговых ботов."""

    # BYBIT_FUTURES = "BYBIT_FUTURES"
    # """Торговый бот для торговли на Биткойне на Битфьюрках."""
    # BINGX_FUTURES = "BINGX_FUTURES"  # новый

class TradebotType(str, Enum):
        BYBIT_FUTURES = "bybit_futures"
        BINGX_FUTURES = "bingx_futures"  # новый тип

class SignalSide(StrEnum):
    """Перечисление типов сигналов."""

    BUY = "BUY"
    """Сигнал на покупку."""

    SELL = "SELL"
    """Сигнал на продажу."""
