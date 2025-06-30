Добавь новую стратегию скринера в мой Торговый робот

Вот структура проекта и текущая логика, ты должен напомнить мне сделать следующие пункты:
- Новый скринер должен быть классом-наследником от `ABCScreener` и размещён в `app/screener/<имя>.py`.
- Нужно добавить новый тип в перечисление `ScreenerType` (в `app/schemas/enums.py`).
- Нужно замапить новый тип и скринер в `SCREENER_MAPPER` в `app/screener/__init__.py`.
- В файле `app/core/config.py` может использоваться тип по умолчанию — его тоже нужно обновить.

Абстракция:
```python
__all__ = ["ABCScreener"]

from abc import ABC, abstractmethod
from collections.abc import Callable

from app.schemas import SignalDTO


class ABCScreener(ABC):
    """Абстракция для создания скринеров."""

    def __init__(self, callback: Callable[[SignalDTO], None], *args, **kwargs) -> None:
        """Инициализация скринера с обратным вызовом и дополнительными аргументами.

        Parameters:
            callback (Callable[[SignalDTO], None]): Функция обратного вызова для обработки сигнала.
            *args: Дополнительные позиционные аргументы.
            **kwargs: Дополнительные именованные аргументы.
        """
        self._callback = callback

    @abstractmethod
    def run(self) -> None:
        """Абстрактный метод для запуска скринера."""
        pass
```

Пример уже реализованных стратегий: `RSIScreener`:
```python
import time
from collections import defaultdict, deque
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from itertools import batched
from typing import Literal

from pybit.unified_trading import MarketHTTP, WebSocket

from app.core import config, logger
from app.schemas import SignalDTO
from app.schemas.enums import SignalSide
from app.schemas.types import KlineDict

from .abstract import ABCScreener


class RSIScreener(ABCScreener):
    """Скринер RSI."""

    ONLY_USDT: bool = True
    """Обработка только USDT-пар."""

    WS_CHUNK_SIZE: int = 10
    """Количество тикеров в одном вебсокет соединении."""

    CATEGORY: Literal["linear", "spot"] = "linear"
    """Категория рынка: фьючерсы или спот."""

    def __init__(
        self,
        callback: Callable[[SignalDTO], None],
        length: int = config.RSI_SCREENER_LENGTH,
        timeframe: int = config.RSI_SCREENER_TIMEFRAME,
        lower_threshold: float = config.RSI_SCREENER_LOWER_THRESHOLD,
        upper_threshold: float = config.RSI_SCREENER_UPPER_THRESHOLD,
    ) -> None:
        """Инициализация скринера с обратным вызовом и дополнительными аргументами."""
        super().__init__(callback)

        self._length: int = length
        self._increased_length: int = (
            self._length * 10
        )  # Увеличенная длинна данных для более точного вычисления RSI (Но снижает производительность)
        self._timeframe: int = timeframe
        self._lower_threshold: float = lower_threshold
        self._upper_threshold: float = upper_threshold

        self._klines: dict[str, deque[KlineDict]] = defaultdict(
            lambda: deque(maxlen=self._increased_length)
        )  # От количества свечей напрямую зависит точность вычисления RSI

        self._market_http = MarketHTTP(testnet=False)

    def run(self) -> None:
        """Запуск скринера."""
        logger.info(f"Скринер {self.__class__.__name__} запущен")

        # Получаем список тикеров
        tickers = self._get_tickers_list()

        # Разбиваем тикеры на чанки
        ticker_chunks = batched(tickers, self.WS_CHUNK_SIZE)  # noqa

        # Для каждого чанка создаем свое соединение и предварительно собираем свечи
        for batch in ticker_chunks:
            # Важно ждать безопасной зоны для запуска, 45-60 секунда каждой минуты не подходит
            self._wait_for_safe_second_range()

            # Важно быстро собрать свечи и не ждать 10+ пингов
            with ThreadPoolExecutor() as executor:
                executor.map(self._pre_fill_klines, batch)

            WebSocket(self.CATEGORY, testnet=False).kline_stream(
                interval=self._timeframe, symbol=batch, callback=self._on_kline_message
            )
            logger.debug(f"Вебсокет подключения запущены для тикеров: {batch}")
            time.sleep(1)
        logger.info("Все вебсокет соединения запущены")

    def _pre_fill_klines(self, symbol: str) -> None:
        """Предварительный запрос для получения свечей по тикеру,
        чтобы при включении скринера - он мог сразу начать вычислять значение RSI."""
        klines_response = self._market_http.get_kline(
            category=self.CATEGORY,
            symbol=symbol,
            interval=self._timeframe,
            limit=int(
                self._increased_length * 1.5
            ),  # Умножаем т.к. некоторые обьемы могут быть нулевыми
        )
        for k in reversed(klines_response["result"]["list"]):
            volume_usdt = float(k[6])
            if (
                volume_usdt != 0
            ):  # Это сделано, чтобы унифицировать данные с TradingView, !ОБЪЯСНИ ЭТО В ВИДЕО
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
        """Обработка сообщения из WebSocket.
        Документация: https://bybit-exchange.github.io/docs/v5/websocket/public/kline
        """
        try:
            # Парсинг данных из свечи
            ticker = message["topic"].split(".")[-1]
            data = message["data"]  # Вот тут список!
            for el in data:
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
            logger.exception(f"Error handling message ({message}): {e}")

    def _process_new_kline(self, ticker: str, new_kline: KlineDict) -> None:
        """Функция обрабатывает новую свечу."""
        # Добавляем свечу в хранилище или обновляем ее
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

        if is_closed:  # Проверяем свечи только на закрытии
            self._process_klines_queue(ticker, klines)

    def _process_klines_queue(self, ticker: str, klines: deque[KlineDict]) -> None:
        """Функция занимается поиском сигналов в очереди свечей."""
        # Проверка - полностью ли заполнены данные, которые нужны для анализа
        if not len(klines) == klines.maxlen:
            logger.debug(f"{ticker} Kline queue is not full")
            return  # Очередь не полная, проверять нечего

        klines_lst: list[KlineDict] = list(klines)[:-1]  # type: ignore
        curr_rsi = self._calculate_rsi(klines_lst, self._length)
        prev_rsi = self._calculate_rsi(klines_lst[:-1], self._length)
        logger.debug(f"Kline for {ticker} is closed: {curr_rsi=}, {prev_rsi=}")

        signal_side = None

        # Проверка buy сигнала
        if prev_rsi < self._lower_threshold < curr_rsi:
            signal_side = SignalSide.BUY
        # Проверка sell сигнала
        if prev_rsi > self._upper_threshold > curr_rsi:
            signal_side = SignalSide.SELL

        if signal_side:
            return self._callback(
                SignalDTO(
                    symbol=ticker,
                    side=signal_side,
                    klines=klines_lst,
                )
            )

    def _get_tickers_list(self) -> list[str]:
        """Получение списка тикеров."""
        tickers = self._market_http.get_tickers(category=self.CATEGORY)
        if self.ONLY_USDT:
            return [
                ticker["symbol"]
                for ticker in tickers["result"]["list"]  # type: ignore
                if ticker["symbol"].endswith("USDT")
            ]
        return [ticker["symbol"] for ticker in tickers["result"]["list"]]  # type: ignore

    @staticmethod
    def _calculate_rsi(klines: list[KlineDict], period: int) -> float:
        """
        Вычисляет RSI по последним `period + 1` свечам.

        :param klines: Список свечей от старых к новым.
        :param period: Период RSI.
        :return: RSI-значение.
        """

        def rma(values: list[float], period: int) -> list[float]:
            """Wilder's RMA (аналог ta.rma на TradingView)"""
            result = []
            avg = sum(values[:period]) / period
            result.append(avg)
            for val in values[period:]:
                avg = (avg * (period - 1) + val) / period
                result.append(avg)
            return result

        if len(klines) < period + 1:
            raise ValueError("Not enough data to calculate RSI")

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
        rsi = 100 - (100 / (1 + rs))

        # Debug print
        # logger.warning("\n== Debug RSI source data ==")
        # for k in klines:
        #     from datetime import datetime

        #     dt = datetime.fromtimestamp(k["t"] / 1000)
        #     logger.info(f"{dt:%Y-%m-%d %H:%M:%S} — close: {k['c']}")
        # logger.info("==============================\n")
        # logger.info(f"RSI = {rsi:.2f} | gain = {last_gain:.2f}, loss = {last_loss:.2f}")

        return rsi

    def _wait_for_safe_second_range(
        self, min_second: int = 5, max_second: int = 45, check_interval: float = 0.1
    ) -> None:
        """
        Блокирует текущий поток до тех пор, пока текущее значение секунд (UTC)
        не попадёт в указанный диапазон [min_second, max_second].

        Используется, например, для синхронного запуска задач в определённом временном окне.

        :param min_second: минимальное значение секунд (включительно), по умолчанию 5
        :param max_second: максимальное значение секунд (включительно), по умолчанию 45
        :param check_interval: как часто проверять время (в секундах), по умолчанию 0.1
        """
        while True:
            current_second = datetime.now().second
            if min_second <= current_second <= max_second:
                break
            time.sleep(check_interval)

```

Моя стратегия: <вставь описание своей стратегии — с логикой фильтрации> (если пользователь я забыл подставить стратегию под плейсхолдер дай мне несколько вариантов стратегий, которые ты можешь реализовать в точности как на трейдингвью и какие считаешь относительно прибыльными.)

Сгенерируй мне:
1. Полный класс скринера, который мне можно просто скопировать.
2. Что именно вставить и куда — по файлам и поэтапно.
