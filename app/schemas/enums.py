__all__ = ["ScreenerType", "TradebotType", "SignalSide"]

from enum import StrEnum


class ScreenerType(StrEnum):
    """Перечисление типов скринеров."""

    RSI = "RSI"
    """Скринер, который генерирует сигналы в соответствии с индикатором RSI."""


class TradebotType(StrEnum):
    """Перечисление типов торговых ботов."""

    BYBIT_FUTURES = "BYBIT_FUTURES"
    """Торговый бот для торговли на Биткойне на Битфьюрках."""


class SignalSide(StrEnum):
    """Перечисление типов сигналов."""

    BUY = "BUY"
    """Сигнал на покупку."""

    SELL = "SELL"
    """Сигнал на продажу."""
