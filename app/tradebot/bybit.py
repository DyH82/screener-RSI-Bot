__all__ = ["BybitTradebot"]

from typing import Literal

import pybit.exceptions
from pybit.unified_trading import HTTP

from app.core import config, logger
from app.schemas import SignalDTO
from app.schemas.enums import SignalSide

from .abstract import ABCTradebot
from .bybit_exchange_info import BybitExchangeInfo


class BybitTradebot(ABCTradebot):
    """Класс, который исполняет сигнал (открывает позицию, выставляет тп и сл)."""

    CATEGORY: Literal["linear", "spot"] = "linear"
    """Категория рынка: фьючерсы или спот."""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        take_profit: float | None = config.TAKE_PROFIT,
        stop_loss: float | None = config.STOP_LOSS,
        leverage: int | None = config.LEVERAGE,
        max_allowed_positions: int | None = config.MAX_ALLOWED_POSITIONS,
        usdt_quantity: float = config.USDT_QUANTITY,
    ) -> None:
        """Инициализация класса BybitFuturesTradebot."""
        self._client = HTTP(api_key=api_key, api_secret=api_secret)

        self._take_profit: float | None = take_profit
        self._stop_loss: float | None = stop_loss
        self._leverage: int | None = leverage
        self._max_allowed_positions: int | None = max_allowed_positions
        self._usdt_quantity: float = usdt_quantity

        self._exchange_info = BybitExchangeInfo()
        self._exchange_info.start()

    def process_signal(self, signal: SignalDTO) -> None:
        """Обработка сигнала (открытие позиции, выставление тп и сл)."""
        repr = f"[{signal.symbol}:{signal.side}]"
        try:
            logger.info(f"{repr} Начинаю обработку сигнала")

            # Проверяем открытые позиции и их количество
            if not self._check_positions_status(signal.symbol):
                logger.info(
                    f"{repr} Невозможно открыть позицию, т.к. "
                    "уже превышен лимит открытых позиций или "
                    "позиция по тикеру уже открыта"
                )
                return

            # Устанавливаем нужное торговое плечо
            self._set_leverage(signal.symbol)

            # Высчитываем цены и размеры
            quantity = self._calculate_quantity(signal.symbol, signal.last_price)
            stop_loss = self._calculate_sl_price(signal.symbol, signal.last_price, signal.side)
            take_profit = self._calculate_tp_price(signal.symbol, signal.last_price, signal.side)

            # Откроем маркет ордер с тейком и стопом
            self._place_market_order(
                symbol=signal.symbol,
                quantity=quantity,
                side=signal.side,
                stop_loss=stop_loss,
                take_profit=take_profit,
            )
        except Exception as e:
            logger.exception(f"{repr} Ошибка при обработке сигнала ({signal}): {e}")
        finally:
            logger.info(f"{repr} Закончил обработку сигнала")

    def _check_positions_status(self, symbol: str) -> bool:
        """Проверка: Не открыта ли текущая позиция и проверка общего количества позиций"""

        def _check_current_position_status(positions: list[dict], symbol: str) -> bool:
            """Проверка текущей открытой позиции."""
            return symbol not in positions

        def _check_max_allowed_positions(positions: list[dict]) -> bool:
            """Проверка максимального количества позиций."""
            return (
                self._max_allowed_positions is None or len(positions) < self._max_allowed_positions
            )

        positions_raw = self._client.get_positions(category=self.CATEGORY, settleCoin="USDT")
        positions: list[dict] = [p["symbol"] for p in positions_raw["result"]["list"]]  # type: ignore

        return _check_current_position_status(
            positions=positions, symbol=symbol
        ) and _check_max_allowed_positions(positions=positions)

    def _set_leverage(self, symbol: str) -> None:
        """Установка плеча для указанной пары."""
        if self._leverage:
            try:
                self._client.set_leverage(
                    symbol=symbol,
                    buyLeverage=str(self._leverage),
                    sellLeverage=str(self._leverage),
                    category=self.CATEGORY,
                )
                logger.info(f"Плечо на {symbol} изменено на {self._leverage}X")
            except pybit.exceptions.InvalidRequestError as e:
                if e.status_code == 110043:
                    logger.info(f"Плечо на {symbol} уже установлено на {self._leverage}X")
                    return
                raise
        else:
            logger.debug(f"Плечо на {symbol} изменять не нужно")

    def _place_market_order(
        self,
        symbol: str,
        quantity: float,
        side: SignalSide,
        stop_loss: float | None,
        take_profit: float | None,
    ) -> None:
        """Создание рыночного ордера для указанной пары."""
        kwargs = dict(
            symbol=symbol,
            side=side.capitalize(),
            orderType="Market",
            qty=quantity,
            category=self.CATEGORY,
        )
        if stop_loss:
            kwargs["stopLoss"] = stop_loss
        if take_profit:
            kwargs["takeProfit"] = take_profit
        response = self._client.place_order(**kwargs)
        logger.info(f"[{symbol}:{side}] Рыночный ордер создан: {response}")

    def _calculate_tp_price(self, symbol: str, last_price: float, side: SignalSide) -> float | None:
        """Расчет цены для тейк-профита."""
        if not self._take_profit:
            return None
        if side == SignalSide.BUY:
            tp_price = last_price * (1 + self._take_profit / 100)
        elif side == SignalSide.SELL:
            tp_price = last_price * (1 - self._take_profit / 100)
        else:
            raise ValueError(f"Неподдерживаемый тип сигнала: {side}")
        return self._exchange_info.round_price(symbol, tp_price)

    def _calculate_sl_price(self, symbol: str, last_price: float, side: SignalSide) -> float | None:
        """Расчет цены для стоп-лосса."""
        if not self._stop_loss:
            return None
        if side == SignalSide.BUY:
            sl_price = last_price * (1 - self._stop_loss / 100)
        elif side == SignalSide.SELL:
            sl_price = last_price * (1 + self._stop_loss / 100)
        else:
            raise ValueError(f"Неподдерживаемый тип сигнала: {side}")
        return self._exchange_info.round_price(symbol, sl_price)

    def _calculate_quantity(self, symbol: str, last_price: float) -> float:
        """Расчет количества для рыночного ордера."""
        return self._exchange_info.round_quantity(symbol, self._usdt_quantity / last_price)
