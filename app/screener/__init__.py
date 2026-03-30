__all__ = ["ABCScreener", "SCREENER_MAPPER"]

# from app.schemas import ScreenerType
#
# from .abstract import ABCScreener
# from .ema import EMAScreener
# from .rsi import RSIScreener
#
# SCREENER_MAPPER: dict[ScreenerType, type[ABCScreener]] = {
#     ScreenerType.RSI: RSIScreener,
#     ScreenerType.EMA: EMAScreener,
# }
# """Маппер скринеров по типу. При добавлении нового типа скринера нужно:
# 1. Добавить его тип в ScreenerType
# 2. Замапить новый тип с новым скринером в SCREENER_MAPPER
# """
from .rsi import RSIScreener
from .ema import EMAScreener
from .abstract import ABCScreener
from app.schemas.enums import ScreenerType

SCREENER_MAPPER = {
    ScreenerType.RSI: RSIScreener,
    ScreenerType.EMA: EMAScreener,
}