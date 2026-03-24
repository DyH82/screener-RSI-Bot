__all__ = ["BingxTradebot"]

import json
import time
import hashlib
import hmac
from typing import Literal

import requests
import ccxt
from ccxt.base.errors import RateLimitExceeded

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
        self.api_key = api_key
        self.api_secret = api_secret
        self._take_profit = take_profit
        self._stop_loss = stop_loss
        self._leverage = leverage
        self._max_allowed_positions = max_allowed_positions
        self._usdt_quantity = usdt_quantity
        self.use_demo = use_demo

        self.base_url = "https://open-api-vst.bingx.com" if use_demo else "https://open-api.bingx.com"

        # CCXT для позиций и плеча
        self.exchange = ccxt.bingx({
            'apiKey': api_key,
            'secret': api_secret,
            'options': {'defaultType': 'swap'},
        })
        if use_demo:
            self.exchange.set_sandbox_mode(True)

        # Получение информации о символах (точность, оригинальные имена)
        self._exchange_info = BingxExchangeInfo()
        self._exchange_info.start()

        # Кэш позиций
        self._positions_cache = None
        self._positions_cache_time = 0
        self._positions_cache_ttl = 5

    def _sign_request(self, params: dict) -> str:
        """Создаёт подпись HMAC-SHA256 для параметров."""
        query_string = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
        return hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

    def _get_positions(self) -> list[dict]:
        """Получает открытые позиции через CCXT (с кэшированием)."""
        now = time.time()
        if self._positions_cache is not None and (now - self._positions_cache_time) < self._positions_cache_ttl:
            return self._positions_cache

        max_retries = 3
        for attempt in range(max_retries):
            try:
                positions = self.exchange.fetch_positions()
                self._positions_cache = [
                    {"symbol": p["symbol"].replace("-", "").replace("/", ""), "side": p["side"]}
                    for p in positions if float(p["contracts"]) > 0
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
        """Устанавливает плечо через CCXT."""
        if not self._leverage:
            return
        symbol_original = self._exchange_info.get_original_symbol(symbol_clean)
        max_retries = 3
        for attempt in range(max_retries):
            try:
                self.exchange.set_leverage(self._leverage, symbol_original, {'side': 'LONG'})
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
        """Размещает рыночный ордер с TP/SL через прямой запрос к API (числа, не строки)."""
        symbol_original = self._exchange_info.get_original_symbol(symbol_clean)
        endpoint = "/openApi/swap/v2/trade/order"

        # Базовые параметры (числа, не строки)
        params = {
            "symbol": symbol_original,
            "side": side.value.upper(),
            "positionSide": "LONG" if side == SignalSide.BUY else "SHORT",
            "type": "MARKET",
            "quantity": quantity,  # число
            "recvWindow": 5000,  # число
            "timestamp": int(time.time() * 1000),  # число
        }

        # Добавляем TP/SL как JSON-строки, но внутри числа (не строки)
        if take_profit is not None:
            params["takeProfit"] = json.dumps({
                "type": "TAKE_PROFIT_MARKET",
                "stopPrice": take_profit,  # число
                "price": take_profit,  # число
                "workingType": "MARK_PRICE"
            })
        if stop_loss is not None:
            params["stopLoss"] = json.dumps({
                "type": "STOP_MARKET",
                "stopPrice": stop_loss,  # число
                "price": stop_loss,  # число
                "workingType": "MARK_PRICE"
            })

        # Формируем подпись (сортировка ключей)
        sorted_keys = sorted(params.keys())
        query_string = "&".join([f"{k}={params[k]}" for k in sorted_keys])
        signature = self._sign_request({k: params[k] for k in sorted_keys})
        url = f"{self.base_url}{endpoint}?{query_string}&signature={signature}"
        headers = {"X-BX-APIKEY": self.api_key}

        try:
            response = requests.post(url, headers=headers)
            data = response.json()
            if data.get("code") != 0:
                raise Exception(f"Bingx API error: {data}")
            order_data = data.get("data", {}).get("order", {})
            logger.info(
                f"[{symbol_clean}:{side}] Ордер {order_data.get('orderId')} исполнен: "
                f"цена={order_data.get('avgPrice')}, кол-во={order_data.get('executedQty')}"
            )
            if config.LOG_API_DETAILS:
                logger.debug(f"Полный ответ: {data}")
        except Exception as e:
            logger.error(f"Ошибка при создании ордера: {e}")
            raise

        # Формируем подпись (параметры сортируем, добавляем recvWindow)
        params["recvWindow"] = "5000"
        sorted_keys = sorted(params.keys())
        query_string = "&".join([f"{k}={params[k]}" for k in sorted_keys])
        signature = self._sign_request({k: params[k] for k in sorted_keys})
        url = f"{self.base_url}{endpoint}?{query_string}&signature={signature}"
        headers = {"X-BX-APIKEY": self.api_key}

        try:
            response = requests.post(url, headers=headers)
            data = response.json()
            if data.get("code") != 0:
                raise Exception(f"Bingx API error: {data}")
            order_data = data.get("data", {}).get("order", {})
            logger.info(
                f"[{symbol_clean}:{side}] Ордер {order_data.get('orderId')} исполнен: "
                f"цена={order_data.get('avgPrice')}, кол-во={order_data.get('executedQty')}"
            )
            if config.LOG_API_DETAILS:
                logger.debug(f"Полный ответ: {data}")
        except Exception as e:
            logger.error(f"Ошибка при создании ордера: {e}")
            raise

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