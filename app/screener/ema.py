import time
from collections import defaultdict, deque
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from app.core import config, logger
from app.schemas import SignalDTO
from app.schemas.enums import SignalSide
from app.schemas.types import KlineDict
from app.tradebot.bingx_exchange_info import BingxExchangeInfo

from .abstract import ABCScreener


class EMAScreener(ABCScreener):
    ONLY_USDT: bool = True
    CATEGORY: Literal["linear", "spot"] = "linear"

    def __init__(
        self,
        callback: Callable[[SignalDTO], None],
        short_period: int = 9,
        long_period: int = 21,
        timeframe: int = 5,
    ) -> None:
        super().__init__(callback)
        self._short_period = short_period
        self._long_period = long_period
        self._timeframe = timeframe
        self._needed_klines = long_period + 5
        self._klines: dict[str, deque[KlineDict]] = defaultdict(
            lambda: deque(maxlen=self._needed_klines)
        )
        self._symbols = []

    def run(self) -> None:
        logger.info(f"Скринер {self.__class__.__name__} запущен (данные BingX)")
        self._symbols = self._get_tickers_list()
        if not self._symbols:
            logger.error("Не удалось получить список символов")
            return

        with ThreadPoolExecutor(max_workers=10) as executor:
            executor.map(self._pre_fill_klines, self._symbols)

        interval_seconds = self._timeframe * 60
        while True:
            time.sleep(interval_seconds)
            with ThreadPoolExecutor(max_workers=10) as executor:
                executor.map(self._update_klines, self._symbols)

    def _pre_fill_klines(self, symbol: str) -> None:
        klines = BingxExchangeInfo.fetch_klines(
            symbol, self._interval_to_str(self._timeframe), self._needed_klines
        )
        if klines:
            self._klines[symbol] = deque(klines, maxlen=self._needed_klines)
            logger.debug(f"Загружено {len(klines)} свечей для {symbol}")
        else:
            logger.warning(f"Не удалось загрузить историю для {symbol}")

    def _update_klines(self, symbol: str) -> None:
        klines = BingxExchangeInfo.fetch_klines(
            symbol, self._interval_to_str(self._timeframe), 2
        )
        if not klines:
            return
        new_kline = klines[-1]
        current = self._klines[symbol]
        if current and current[-1]['t'] == new_kline['t']:
            return
        current.append(new_kline)
        if len(current) >= self._long_period + 2:
            self._process_klines_queue(symbol, current)

    @staticmethod
    def _interval_to_str(minutes: int) -> str:
        if minutes == 1:
            return "1m"
        elif minutes == 5:
            return "5m"
        elif minutes == 15:
            return "15m"
        elif minutes == 30:
            return "30m"
        elif minutes == 60:
            return "1h"
        elif minutes == 120:
            return "2h"
        elif minutes == 240:
            return "4h"
        elif minutes == 360:
            return "6h"
        elif minutes == 720:
            return "12h"
        else:
            return f"{minutes}m"

    def _process_klines_queue(self, ticker: str, klines: deque[KlineDict]) -> None:
        if len(klines) < self._long_period + 2:
            return
        closes = [k["c"] for k in klines]
        ema_short_prev = self._calculate_ema(closes[:-1], self._short_period)
        ema_long_prev = self._calculate_ema(closes[:-1], self._long_period)
        ema_short_curr = self._calculate_ema(closes, self._short_period)
        ema_long_curr = self._calculate_ema(closes, self._long_period)

        signal = None
        if ema_short_prev < ema_long_prev and ema_short_curr > ema_long_curr:
            signal = SignalSide.BUY
        elif ema_short_prev > ema_long_prev and ema_short_curr < ema_long_curr:
            signal = SignalSide.SELL

        if signal:
            self._callback(SignalDTO(symbol=ticker, side=signal, klines=list(klines)))

    def _get_tickers_list(self) -> list[str]:
        """Возвращает список активных фьючерсных символов с BingX."""
        for _ in range(100):
            if BingxExchangeInfo.original_symbols:
                break
            time.sleep(0.1)
        if not BingxExchangeInfo.original_symbols:
            logger.error("Не удалось получить список символов от Bingx")
            return []
        all_symbols = list(BingxExchangeInfo.original_symbols.values())
        if self.ONLY_USDT:
            return [s for s in all_symbols if s.endswith("USDT")]
        return all_symbols

    @staticmethod
    def _calculate_ema(closes: list[float], period: int) -> float:
        if len(closes) < period:
            return 0.0
        k = 2 / (period + 1)
        ema = sum(closes[:period]) / period
        for price in closes[period:]:
            ema = price * k + ema * (1 - k)
        return ema