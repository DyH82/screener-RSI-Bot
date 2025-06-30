__all__ = ["KlineDict"]


from typing import TypedDict


class KlineDict(TypedDict):
    """Модель свечи."""

    t: int  # open time
    o: float  # open price
    h: float  # high price
    l: float  # low price
    c: float  # close price
    v: float  # volume (USDT)
