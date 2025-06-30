__all__ = [
    "SignalDTO",
]

from dataclasses import dataclass, field

from app.schemas.types import KlineDict

from .enums import SignalSide


@dataclass
class SignalDTO:
    """DTO сигнала, которое передается внутри приложения."""

    symbol: str
    """Торговая пара."""

    side: SignalSide
    """Сторона сигнала."""

    prev_rsi: float
    """RSI на одну свечу назад."""

    curr_rsi: float
    """RSI на текущий момент."""

    klines: list[KlineDict] = field(repr=False)
    """Список свечей которые были использованы для анализа."""

    @property
    def last_price(self) -> float:
        """Актуальная цена на момент сигнала."""
        return self.klines[-1]["c"]
