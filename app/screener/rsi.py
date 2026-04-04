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
        self._klines: dict[str, deque[KlineDict]] = {}
        self._symbols = []

        # Настройки фильтров
        self._use_volume_filter = getattr(config, 'USE_VOLUME_FILTER', False)
        self._volume_multiplier = getattr(config, 'VOLUME_MULTIPLIER', 1.5)
        self._volume_period = getattr(config, 'VOLUME_PERIOD', 10)

    def run(self) -> None:
        logger.info(f"Скринер {self.__class__.__name__} запущен (REST BingX)")
        if self._use_volume_filter:
            logger.info(f"Фильтр объёма ВКЛЮЧЁН: множитель={self._volume_multiplier}, период={self._volume_period}")
        self._symbols = self._get_tickers_list()
        if not self._symbols:
            logger.error("Не удалось получить список символов")
            return
        logger.info(f"Отслеживаем {len(self._symbols)} символов")

        # Инициализация очередей и предзагрузка истории
        for symbol in self._symbols:
            self._klines[symbol] = deque(maxlen=self._needed_klines)
            self._pre_fill_klines(symbol)
            time.sleep(0.5)

        interval_seconds = self._timeframe * 60
        while True:
            start_time = time.time()
            for symbol in self._symbols:
                self._update_klines(symbol)
                time.sleep(0.1)
            elapsed = time.time() - start_time
            if elapsed < interval_seconds:
                time.sleep(interval_seconds - elapsed)

    def _pre_fill_klines(self, symbol: str) -> None:
        klines = BingxExchangeInfo.fetch_klines(
            symbol, self._interval_to_str(self._timeframe), self._needed_klines
        )
        if klines:
            self._klines[symbol].extend(klines)
            logger.debug(f"Загружено {len(klines)} свечей для {symbol}")
        else:
            logger.warning(f"Не удалось загрузить историю для {symbol}")

    def _update_klines(self, symbol: str) -> None:
        klines = BingxExchangeInfo.fetch_klines(
            symbol, self._interval_to_str(self._timeframe), 2
        )
        if not klines:
            return
        if len(klines) < 2:
            return
        closed_candle = klines[-2]
        current = self._klines.get(symbol)
        if current is None:
            return
        if current and current[-1]['t'] == closed_candle['t']:
            return
        current.append(closed_candle)
        logger.debug(
            f"✅ Новая свеча для {symbol}: close={closed_candle['c']}, время={closed_candle['t']}, очередь={len(current)}")
        if len(current) >= self._length + 1:
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

    def _check_volume_filter(self, klines: deque[KlineDict]) -> bool:
        """Проверяет, превышает ли текущий объём средний."""
        if not self._use_volume_filter:
            return True

        if len(klines) < self._volume_period:
            return True

        volumes = [k["v"] for k in list(klines)[-self._volume_period:]]
        avg_volume = sum(volumes) / len(volumes)
        current_volume = klines[-1]["v"]

        result = current_volume > avg_volume * self._volume_multiplier
        if not result:
            logger.debug(
                f"Фильтр объёма: текущий={current_volume:.2f}, средний={avg_volume:.2f}, множитель={self._volume_multiplier}")
        return result

    def _process_klines_queue(self, ticker: str, klines: deque[KlineDict]) -> None:
        if len(klines) < self._length + 1:
            return
        klines_lst = list(klines)
        curr_rsi = self._calculate_rsi(klines_lst, self._length)
        prev_rsi = self._calculate_rsi(klines_lst[:-1], self._length)

        logger.info(
            f"📊 {ticker}: prev_rsi={prev_rsi:.1f}, curr_rsi={curr_rsi:.1f}, lower={self._lower_threshold}, upper={self._upper_threshold}")

        signal_side = None
        if prev_rsi < self._lower_threshold < curr_rsi:
            signal_side = SignalSide.BUY
        elif prev_rsi > self._upper_threshold > curr_rsi:
            signal_side = SignalSide.SELL

        if signal_side:
            if not self._check_volume_filter(klines):
                logger.info(f"🔇 {ticker}: сигнал {signal_side.value} отфильтрован по объёму")
                return
            logger.info(f"🔔 СИГНАЛ {ticker}: {signal_side.value}")
            self._callback(SignalDTO(symbol=ticker, side=signal_side, klines=klines_lst))

    def _get_tickers_list(self) -> list[str]:
        for _ in range(100):
            if BingxExchangeInfo.original_symbols:
                break
            time.sleep(0.1)
        if not BingxExchangeInfo.original_symbols:
            logger.error("Не удалось получить список символов BingX")
            return []
        all_symbols = list(BingxExchangeInfo.original_symbols.values())
        if self.ONLY_USDT:
            all_symbols = [s for s in all_symbols if s.endswith("-USDT")]
        max_symbols = getattr(config, 'MAX_SYMBOLS', 200)
        return all_symbols[:max_symbols]

    @staticmethod
    def _calculate_rsi(klines: list[KlineDict], period: int) -> float:
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