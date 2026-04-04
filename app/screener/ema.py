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
            short_period: int = config.EMA_SCREENER_SHORT_PERIOD,
            long_period: int = config.EMA_SCREENER_LONG_PERIOD,
            trend_period: int = config.EMA_SCREENER_TREND_PERIOD,
            timeframe: int = config.EMA_SCREENER_TIMEFRAME,
    ) -> None:
        super().__init__(callback)
        self._min_move_percent = None
        self._short_period = short_period
        self._long_period = long_period
        self._trend_period = trend_period
        self._timeframe = timeframe
        self._needed_klines = max(trend_period + 5, 50)
        self._klines: dict[str, deque[KlineDict]] = {}
        self._symbols = []

        # Настройки MACD
        self._macd_fast = getattr(config, 'MACD_FAST_PERIOD', 12)
        self._macd_slow = getattr(config, 'MACD_SLOW_PERIOD', 26)
        self._macd_signal = getattr(config, 'MACD_SIGNAL_PERIOD', 9)

        # Настройки RSI подтверждения
        self._use_rsi_confirmation = getattr(config, 'USE_RSI_CONFIRMATION', True)
        self._rsi_period = getattr(config, 'RSI_CONFIRMATION_PERIOD', 14)
        self._rsi_threshold = getattr(config, 'RSI_CONFIRMATION_THRESHOLD', 40.0)

        # Настройки фильтров
        self._use_volume_filter = getattr(config, 'USE_VOLUME_FILTER', False)
        self._volume_multiplier = getattr(config, 'VOLUME_MULTIPLIER', 1.5)
        self._volume_period = getattr(config, 'VOLUME_PERIOD', 10)
        self._min_ema_spread = getattr(config, 'MIN_EMA_SPREAD_PERCENT', 0.15)

    def run(self) -> None:
        logger.info(f"Скринер {self.__class__.__name__} запущен (REST BingX)")
        logger.info(f"EMA: {self._short_period}/{self._long_period}/{self._trend_period}")
        if self._use_rsi_confirmation:
            logger.info(f"RSI подтверждение: период={self._rsi_period}, порог={self._rsi_threshold}")
        self._symbols = self._get_tickers_list()
        if not self._symbols:
            logger.error("Не удалось получить список символов")
            return
        logger.info(f"Отслеживаем {len(self._symbols)} символов")

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
        if not klines or len(klines) < 2:
            return
        closed_candle = klines[-2]
        current = self._klines.get(symbol)
        if current is None:
            return
        if current and current[-1]['t'] == closed_candle['t']:
            return
        current.append(closed_candle)
        if len(current) >= self._trend_period + 5:
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

    def _calculate_ema(self, closes: list[float], period: int) -> float:
        if len(closes) < period:
            return 0.0
        k = 2 / (period + 1)
        ema = sum(closes[:period]) / period
        for price in closes[period:]:
            ema = price * k + ema * (1 - k)
        return ema

    def _calculate_macd(self, closes: list[float]) -> tuple[float, float, float]:
        """Возвращает (macd_line, signal_line, histogram)."""
        if len(closes) < self._macd_slow:
            return 0.0, 0.0, 0.0

        fast_ema = self._calculate_ema(closes, self._macd_fast)
        slow_ema = self._calculate_ema(closes, self._macd_slow)
        macd_line = fast_ema - slow_ema

        # Для расчёта сигнальной линии нужно накопить историю MACD
        # Упрощённо: используем EMA от MACD за signal_period
        # Полный расчёт требует хранения значений, пока оставим так
        signal_line = macd_line  # временно
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

    def _calculate_rsi(self, closes: list[float], period: int) -> float:
        if len(closes) < period + 1:
            return 50.0

        changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        gains = [max(c, 0) for c in changes]
        losses = [abs(min(c, 0)) for c in changes]

        def rma(values: list[float], period: int) -> list[float]:
            result = []
            avg = sum(values[:period]) / period
            result.append(avg)
            for val in values[period:]:
                avg = (avg * (period - 1) + val) / period
                result.append(avg)
            return result

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

    def _check_volume_filter(self, klines: deque[KlineDict]) -> bool:
        if not self._use_volume_filter:
            return True
        if len(klines) < self._volume_period:
            return True
        volumes = [k["v"] for k in list(klines)[-self._volume_period:]]
        avg_volume = sum(volumes) / len(volumes)
        current_volume = klines[-1]["v"]
        return current_volume > avg_volume * self._volume_multiplier

    def _process_klines_queue(self, ticker: str, klines: deque[KlineDict]) -> None:
        if len(klines) < self._trend_period + 5:
            return

        closes = [k["c"] for k in klines]

        # Расчёт EMA
        ema_short_curr = self._calculate_ema(closes, self._short_period)
        ema_long_curr = self._calculate_ema(closes, self._long_period)
        ema_trend_curr = self._calculate_ema(closes, self._trend_period)
        ema_short_prev = self._calculate_ema(closes[:-1], self._short_period)
        ema_long_prev = self._calculate_ema(closes[:-1], self._long_period)

        if not self._check_ema_spread(ema_short_curr, ema_long_curr):
            logger.debug(f"{ticker}: EMA spread слишком мал, пропускаем")
            return

        # Расчёт MACD
        macd_line, signal_line, histogram = self._calculate_macd(closes)

        # Расчёт RSI (для подтверждения)
        rsi_value = self._calculate_rsi(closes, self._rsi_period) if self._use_rsi_confirmation else 50.0

        # Логирование
        # logger.info(
        #     f"📊 {ticker}: EMA{self._short_period}={ema_short_curr:.2f}, EMA{self._long_period}={ema_long_curr:.2f}, EMA{self._trend_period}={ema_trend_curr:.2f}, RSI={rsi_value:.1f}")

        # === ЕДИНАЯ ЛОГИКА ВХОДА ===
        signal = None

        # LONG сигнал
        # 1. Цена выше EMA99 (глобальный тренд)
        # 2. EMA7 пересекает EMA25 снизу вверх
        # 3. RSI > порога (подтверждение импульса)
        # 4. MACD > 0 (или пересечение)
        if (closes[-1] > ema_trend_curr and
                ema_short_prev < ema_long_prev and ema_short_curr > ema_long_curr):

            if self._use_rsi_confirmation and rsi_value < self._rsi_threshold:
                logger.debug(f"{ticker}: RSI={rsi_value:.1f} < {self._rsi_threshold}, пропускаем LONG")
            elif macd_line <= 0:
                logger.debug(f"{ticker}: MACD={macd_line:.4f} <= 0, пропускаем LONG")
            else:
                signal = SignalSide.BUY
                logger.info(f"🔔 СИГНАЛ {ticker}: BUY (EMA пересечение, RSI={rsi_value:.1f}, MACD={macd_line:.4f})")

        # SHORT сигнал (зеркально)
        elif (closes[-1] < ema_trend_curr and
              ema_short_prev > ema_long_prev and ema_short_curr < ema_long_curr):

            if self._use_rsi_confirmation and rsi_value > (100 - self._rsi_threshold):
                logger.debug(f"{ticker}: RSI={rsi_value:.1f} > {100 - self._rsi_threshold}, пропускаем SHORT")
            elif macd_line >= 0:
                logger.debug(f"{ticker}: MACD={macd_line:.4f} >= 0, пропускаем SHORT")
            else:
                signal = SignalSide.SELL
                logger.info(f"🔔 СИГНАЛ {ticker}: SELL (EMA пересечение, RSI={rsi_value:.1f}, MACD={macd_line:.4f})")

        if signal:
            if not self._check_volume_filter(klines):
                logger.info(f"🔇 {ticker}: сигнал {signal.value} отфильтрован по объёму")
                return
            self._callback(SignalDTO(symbol=ticker, side=signal, klines=list(klines)))

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

    def _check_min_move(self, klines: deque[KlineDict]) -> bool:
        high = max(k["h"] for k in klines[-5:])
        low = min(k["l"] for k in klines[-5:])
        move_percent = (high - low) / low * 100
        return move_percent >= self._min_move_percent

    @staticmethod
    def _calculate_atr(klines: deque[KlineDict], period: int = 14) -> float:
        """Рассчитывает ATR (Average True Range)."""
        if len(klines) < period + 1:
            return 0.0

        tr_values = []
        klines_list = list(klines)

        for i in range(1, period + 1):
            high = klines_list[-i]["h"]
            low = klines_list[-i]["l"]
            prev_close = klines_list[-i - 1]["c"]

            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            tr_values.append(tr)

        return sum(tr_values) / period

    @staticmethod
    def _check_ema_spread(ema_short: float, ema_long: float, min_spread: float = 0.15) -> bool:
        """Проверяет, что расстояние между EMA достаточно для сигнала."""
        spread_percent = abs(ema_short - ema_long) / ema_long * 100
        return spread_percent >= min_spread  # минимум 0.1% расхождения