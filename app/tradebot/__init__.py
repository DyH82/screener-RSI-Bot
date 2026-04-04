__all__ = ["ABCTradebot", "TRADEBOT_MAPPER"]

from app.schemas.enums import TradebotType

from .abstract import ABCTradebot
# from .bybit import BybitTradebot
from .bingx import BingxTradebot

TRADEBOT_MAPPER: dict[TradebotType, type[ABCTradebot]] = {
    # TradebotType.BYBIT_FUTURES: BybitTradebot,
    TradebotType.BINGX_FUTURES: BingxTradebot,
}
"""Маппер трейдботов по типу. При добавлении нового типа трейдбота нужно:
1. Добавить его тип в TradebotType
2. Замапить новый тип с новым трейдботом в TRADEBOT_MAPPER
"""
