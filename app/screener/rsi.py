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


class RSIScreener(ABCScreener):
    ONLY_USDT: bool = True
    CATEGORY: Literal["linear", "spot"] = "linear"

    def __init__(
        self,
        callback: Callable[[SignalDTO], None],
        length: int = config.RSI_SCREENER_LENGTH,
        timeframe: int = config.RSI_SCREENER_TIMEFRAME,
        lower_threshold: float = config.RSI_SCREENER_LOWER_THRESHOLD,
        upper_threshold: float = config.RSI_SCREENER_UPPER_THRESHOLD,
    ) -> None:
        super().__init__(callback)
        self._length = length
        self._timeframe = timeframe
        self._lower_threshold = lower_threshold
        self._upper_threshold = upper_threshold
        self._needed_klines = length * 10
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

        # Предварительно загружаем историю
        with ThreadPoolExecutor(max_workers=10) as executor:
            executor.map(self._pre_fill_klines, self._symbols)

        # Цикл опроса
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
        """Загружает последние свечи и обновляет очередь."""
        klines = BingxExchangeInfo.fetch_klines(
            symbol, self._interval_to_str(self._timeframe), 2
        )
        if not klines:
            return
        # klines уже от старых к новым, берём последнюю (закрытую)
        new_kline = klines[-1]
        current = self._klines[symbol]
        if current and current[-1]['t'] == new_kline['t']:
            return
        current.append(new_kline)
        if len(current) >= self._length + 1:
            self._process_klines_queue(symbol, current)

    @staticmethod
    def _interval_to_str(minutes: int) -> str:
        """Преобразует минуты в строку интервала BingX."""
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
        """Расчёт RSI и отправка сигнала."""
        if len(klines) < self._length + 1:
            return
        klines_lst = list(klines)
        curr_rsi = self._calculate_rsi(klines_lst, self._length)
        prev_rsi = self._calculate_rsi(klines_lst[:-1], self._length)
        logger.debug(f"Kline for {ticker} is closed: {curr_rsi=}, {prev_rsi=}")

        signal_side = None
        if prev_rsi < self._lower_threshold < curr_rsi:
            signal_side = SignalSide.BUY
        elif prev_rsi > self._upper_threshold > curr_rsi:
            signal_side = SignalSide.SELL

        if signal_side:
            self._callback(SignalDTO(symbol=ticker, side=signal_side, klines=klines_lst))

    def _get_tickers_list(self) -> list[str]:
        """Возвращает список активных фьючерсных символов с BingX, исключая экзотические пары."""
        for _ in range(100):
            if BingxExchangeInfo.original_symbols:
                break
            time.sleep(0.1)
        if not BingxExchangeInfo.original_symbols:
            logger.error("Не удалось получить список символов от Bingx")
            return []
        all_symbols = list(BingxExchangeInfo.original_symbols.values())
        if self.ONLY_USDT:
            filtered = []
            for s in all_symbols:
                if not s.endswith("-USDT"):
                    continue
                # Исключаем товарные и индексные пары
                if s.startswith(("NCS", "NCCO", "NCFX")):
                    continue
                filtered.append(s)
            return filtered
        return all_symbols

    @staticmethod
    def _calculate_rsi(klines: list[KlineDict], period: int) -> float:
        """Вычисляет RSI по списку свечей."""
        def rma(values: list[float], period: int) -> list[float]:
            result = []
            avg = sum(values[:period]) / period
            result.append(avg)
            for val in values[period:]:
                avg = (avg * (period - 1) + val) / period
                result.append(avg)
            return result

        if len(klines) < period + 1:
            return 50.0

        closes = [k["c"] for k in klines]
        changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        gains = [max(c, 0) for c in changes]
        losses = [abs(min(c, 0)) for c in changes]

        avg_gains = rma(gains, period)
        avg_losses = rma(losses, period)

        last_gain = avg_gains[-1]
        last_loss = avg_losses[-1]

        if last_loss == 0:
            return 100.0
        if last_gain == 0:
            return 0.0

        rs = last_gain / last_loss
        return 100 - (100 / (1 + rs))