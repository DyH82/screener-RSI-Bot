import time
from collections import defaultdict, deque
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from itertools import batched
from typing import Literal

from pybit.unified_trading import MarketHTTP, WebSocket

from app.core import logger
from app.schemas import SignalDTO
from app.schemas.enums import SignalSide
from app.schemas.types import KlineDict

from .abstract import ABCScreener


class EMAScreener(ABCScreener):
    """Скринер по стратегии EMA Crossover."""

    ONLY_USDT: bool = True
    WS_CHUNK_SIZE: int = 10
    CATEGORY: Literal["linear", "spot"] = "linear"

    def __init__(
        self,
        callback: Callable[[SignalDTO], None],
        short_period: int = 9,
        long_period: int = 21,
        timeframe: int = 1,
    ) -> None:
        super().__init__(callback)
        self._short = short_period
        self._long = long_period
        self._timeframe = timeframe
        self._needed_klines = long_period + 5

        self._klines: dict[str, deque[KlineDict]] = defaultdict(
            lambda: deque(maxlen=self._needed_klines)
        )
        self._market_http = MarketHTTP(testnet=False)

    def run(self) -> None:
        logger.info(f"Скринер {self.__class__.__name__} запущен")
        tickers = self._get_tickers_list()
        ticker_chunks = batched(tickers, self.WS_CHUNK_SIZE)  # noqa

        for batch in ticker_chunks:
            self._wait_for_safe_second_range()
            with ThreadPoolExecutor() as executor:
                executor.map(self._pre_fill_klines, batch)

            WebSocket(self.CATEGORY, testnet=False).kline_stream(
                interval=self._timeframe,
                symbol=batch,
                callback=self._on_kline_message,
            )
            time.sleep(1)

        logger.info("Все вебсокет соединения запущены")

    def _pre_fill_klines(self, symbol: str) -> None:
        klines_response = self._market_http.get_kline(
            category=self.CATEGORY,
            symbol=symbol,
            interval=self._timeframe,
            limit=self._needed_klines * 2,
        )
        for k in reversed(klines_response["result"]["list"]):
            if float(k[6]) != 0:
                self._klines[symbol].append(
                    KlineDict(
                        t=int(k[0]),
                        o=float(k[1]),
                        h=float(k[2]),
                        l=float(k[3]),
                        c=float(k[4]),
                        v=float(k[6]),
                    )
                )

    def _on_kline_message(self, message: dict) -> None:
        try:
            ticker = message["topic"].split(".")[-1]
            for el in message["data"]:
                kline = KlineDict(
                    t=int(el["start"]),
                    o=float(el["open"]),
                    h=float(el["high"]),
                    l=float(el["low"]),
                    c=float(el["close"]),
                    v=float(el["turnover"]),
                )
                self._process_new_kline(ticker, kline)
        except Exception as e:
            logger.exception(f"Ошибка при обработке сообщения: {e}")

    def _process_new_kline(self, ticker: str, new_kline: KlineDict) -> None:
        klines = self._klines[ticker]
        if klines:
            is_closed = klines[-1]["t"] < new_kline["t"]
            if is_closed:
                klines.append(new_kline)
            else:
                klines[-1] = new_kline
        else:
            is_closed = False
            klines.append(new_kline)

        if is_closed:
            self._process_klines_queue(ticker, klines)

    def _process_klines_queue(self, ticker: str, klines: deque[KlineDict]) -> None:
        if len(klines) < self._long + 2:
            return

        closes = [k["c"] for k in klines]
        ema_short_prev = self._calculate_ema(closes[:-1], self._short)
        ema_long_prev = self._calculate_ema(closes[:-1], self._long)
        ema_short_curr = self._calculate_ema(closes, self._short)
        ema_long_curr = self._calculate_ema(closes, self._long)

        signal = None
        if ema_short_prev < ema_long_prev and ema_short_curr > ema_long_curr:
            signal = SignalSide.BUY
        elif ema_short_prev > ema_long_prev and ema_short_curr < ema_long_curr:
            signal = SignalSide.SELL

        if signal:
            self._callback(SignalDTO(symbol=ticker, side=signal, klines=list(klines)))

    @staticmethod
    def _calculate_ema(closes: list[float], period: int) -> float:
        """Вычисление EMA по формуле TradingView."""
        k = 2 / (period + 1)
        ema = sum(closes[:period]) / period
        for price in closes[period:]:
            ema = price * k + ema * (1 - k)
        return ema

    def _get_tickers_list(self) -> list[str]:
        tickers = self._market_http.get_tickers(category=self.CATEGORY)
        if self.ONLY_USDT:
            return [t["symbol"] for t in tickers["result"]["list"] if t["symbol"].endswith("USDT")]  # type: ignore
        return [t["symbol"] for t in tickers["result"]["list"]]  # type: ignore

    def _wait_for_safe_second_range(
        self, min_second: int = 5, max_second: int = 45, check_interval: float = 0.1
    ) -> None:
        while True:
            now = time.gmtime()
            if min_second <= now.tm_sec <= max_second:
                return
            time.sleep(check_interval)
