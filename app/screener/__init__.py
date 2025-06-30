__all__ = ["ABCScreener", "SCREENER_MAPPER"]

from app.schemas import ScreenerType

from .abstract import ABCScreener
from .rsi import RSIScreener

SCREENER_MAPPER: dict[ScreenerType, type[ABCScreener]] = {
    ScreenerType.RSI: RSIScreener,
}
"""Маппер скринеров по типу. При добавлении нового типа скринера нужно:
1. Добавить его тип в ScreenerType
2. Замапить новый тип с новым скринером в SCREENER_MAPPER
"""
