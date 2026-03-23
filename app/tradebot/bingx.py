__all__ = ["BingxTradebot"]

import json
import time
from typing import Literal

import ccxt
import requests
import hashlib
import hmac
from ccxt.base.errors import ExchangeError, RateLimitExceeded

from app.core import config, logger
from app.schemas import SignalDTO
from app.schemas.enums import SignalSide
from .abstract import ABCTradebot
from .bingx_exchange_info import BingxExchangeInfo


class BingxTradebot(ABCTradebot):
    CATEGORY: Literal["linear", "spot"] = "linear"

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        take_profit: float | None = config.TAKE_PROFIT,
        stop_loss: float | None = config.STOP_LOSS,
        leverage: int | None = config.LEVERAGE,
        max_allowed_positions: int | None = config.MAX_ALLOWED_POSITIONS,
        usdt_quantity: float = config.USDT_QUANTITY,
        use_demo: bool = config.USE_DEMO,
    ) -> None:
        self._take_profit = take_profit
        self._stop_loss = stop_loss
        self._leverage = leverage
        self._max_allowed_positions = max_allowed_positions
        self._usdt_quantity = usdt_quantity
        self.use_demo = use_demo

        # Инициализация CCXT
        self.exchange = ccxt.bingx({
            'apiKey': api_key,
            'secret': api_secret,
            'options': {
                'defaultType': 'swap',      # фьючерсы
            },
        })
        if use_demo:
            self.exchange.set_sandbox_mode(True)

        # Кэш позиций
        self._positions_cache = None
        self._positions_cache_time = 0
        self._positions_cache_ttl = 5

        # Получение информации о символах
        self._exchange_info = BingxExchangeInfo()
        self._exchange_info.start()

    def _get_positions(self) -> list[dict]:
        now = time.time()
        if self._positions_cache is not None and (now - self._positions_cache_time) < self._positions_cache_ttl:
            return self._positions_cache

        max_retries = 3
        for attempt in range(max_retries):
            try:
                positions = self.exchange.fetch_positions()
                self._positions_cache = [
                    {
                        "symbol": pos["symbol"].replace("-", "").replace("/", ""),
                        "side": pos["side"]
                    }
                    for pos in positions if float(pos["contracts"]) > 0
                ]
                self._positions_cache_time = now
                return self._positions_cache
            except RateLimitExceeded:
                wait = 2 ** attempt
                logger.warning(f"Rate limit hit while fetching positions, retrying in {wait}s...")
                time.sleep(wait)
            except Exception as e:
                logger.error(f"Error fetching positions: {e}")
                raise
        logger.error("Failed to fetch positions after retries")
        return []

    def _set_leverage(self, symbol_clean: str) -> None:
        if not self._leverage:
            logger.debug(f"Плечо на {symbol_clean} не меняем")
            return

        symbol_original = self._exchange_info.get_original_symbol(symbol_clean)
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # CCXT требует side в параметрах
                self.exchange.set_leverage(
                    self._leverage,
                    symbol_original,
                    {'side': 'LONG'}
                )
                logger.info(f"Плечо на {symbol_original} установлено на {self._leverage}X")
                return
            except RateLimitExceeded:
                wait = 2 ** attempt
                logger.warning(f"Rate limit hit while setting leverage, retrying in {wait}s...")
                time.sleep(wait)
            except Exception as e:
                logger.error(f"Error setting leverage: {e}")
                raise
        logger.error(f"Failed to set leverage for {symbol_original} after retries")

    def _place_market_order(
        self,
        symbol_clean: str,
        quantity: float,
        side: SignalSide,
        stop_loss: float | None,
        take_profit: float | None,
    ) -> None:
        """Размещает рыночный ордер (без TP/SL) и при необходимости отдельно устанавливает TP/SL."""
        symbol_original = self._exchange_info.get_original_symbol(symbol_clean)
        side_str = "buy" if side == SignalSide.BUY else "sell"

        # Параметры ордера (без TP/SL)
        params = {
            "positionSide": "LONG" if side == SignalSide.BUY else "SHORT",
        }

        try:
            order = self.exchange.create_order(
                symbol=symbol_original,
                type='market',
                side=side_str,
                amount=quantity,
                price=None,
                params=params,
            )
            # Красивый вывод
            logger.info(
                f"[{symbol_clean}:{side}] Ордер {order.get('id')} исполнен: "
                f"цена={order.get('avgPrice')}, кол-во={order.get('filled')}"
            )
            if config.LOG_API_DETAILS:
                logger.debug(f"Полный ответ: {order}")

            # После создания ордера устанавливаем TP/SL отдельным запросом (только на реальном счете)
            if (stop_loss or take_profit) and not self.use_demo:
                position_id = order.get('id')
                if position_id:
                    self._set_tp_sl(symbol_original, position_id, take_profit, stop_loss)
                else:
                    logger.warning(f"[{symbol_clean}:{side}] Не удалось получить positionId для TP/SL")

        except Exception as e:
            logger.error(f"Ошибка при создании ордера: {e}")
            raise

    def _set_tp_sl(self, symbol: str, position_id: str, take_profit: float | None, stop_loss: float | None) -> None:
        """Установка TP/SL через endpoint /openApi/swap/v2/trade/tpSlOrder."""
        endpoint = "/openApi/swap/v2/trade/tpSlOrder"
        params = {
            "positionId": position_id,
            "recvWindow": "5000",
            "timestamp": str(int(time.time() * 1000)),
        }
        if take_profit is not None:
            params["takeProfitPrice"] = str(take_profit)
        if stop_loss is not None:
            params["stopLossPrice"] = str(stop_loss)

        # Подпись
        sorted_keys = sorted(params.keys())
        query_string = "&".join([f"{k}={params[k]}" for k in sorted_keys])
        signature = hmac.new(
            self.exchange.secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        url = f"{self.exchange.urls['api']}{endpoint}?{query_string}&signature={signature}"
        headers = {"X-BX-APIKEY": self.exchange.apiKey}
        try:
            response = requests.post(url, headers=headers)
            data = response.json()
            if data.get("code") != 0:
                raise Exception(f"Bingx API error: {data}")
            logger.info(f"Установлены TP/SL для позиции {position_id}: {data}")
        except Exception as e:
            logger.error(f"Ошибка при установке TP/SL для позиции {position_id}: {e}")

    def _calculate_tp_price(self, symbol: str, last_price: float, side: SignalSide) -> float | None:
        if not self._take_profit:
            return None
        if side == SignalSide.BUY:
            tp_price = last_price * (1 + self._take_profit / 100)
        else:
            tp_price = last_price * (1 - self._take_profit / 100)
        return self._exchange_info.round_price(symbol, tp_price)

    def _calculate_sl_price(self, symbol: str, last_price: float, side: SignalSide) -> float | None:
        if not self._stop_loss:
            return None
        if side == SignalSide.BUY:
            sl_price = last_price * (1 - self._stop_loss / 100)
        else:
            sl_price = last_price * (1 + self._stop_loss / 100)
        return self._exchange_info.round_price(symbol, sl_price)

    def _calculate_quantity(self, symbol: str, last_price: float) -> float:
        qty = self._usdt_quantity / last_price
        return self._exchange_info.round_quantity(symbol, qty)

    def process_signal(self, signal: SignalDTO) -> None:
        repr = f"[{signal.symbol}:{signal.side}]"
        try:
            logger.info(f"{repr} Начинаю обработку сигнала")

            if signal.symbol not in self._exchange_info.original_symbols:
                logger.warning(f"{repr} Символ не найден в списке Bingx, пропускаем")
                return

            if not self._check_positions_status(signal.symbol):
                logger.info(f"{repr} Нельзя открыть позицию (лимит или уже открыта)")
                return

            if self.CATEGORY == "linear":
                self._set_leverage(signal.symbol)

            quantity = self._calculate_quantity(signal.symbol, signal.last_price)
            stop_loss = self._calculate_sl_price(signal.symbol, signal.last_price, signal.side)
            take_profit = self._calculate_tp_price(signal.symbol, signal.last_price, signal.side)

            self._place_market_order(signal.symbol, quantity, signal.side, stop_loss, take_profit)
        except Exception as e:
            logger.exception(f"{repr} Ошибка при обработке сигнала: {e}")
        finally:
            logger.info(f"{repr} Завершил обработку сигнала")

    def _check_positions_status(self, symbol: str) -> bool:
        positions = self._get_positions()
        symbol_exists = any(p["symbol"] == symbol for p in positions)
        if self._max_allowed_positions is not None and len(positions) >= self._max_allowed_positions:
            return False
        return not symbol_exists