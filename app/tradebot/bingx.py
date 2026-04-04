__all__ = ["BingxTradebot"]

import json
import time
import hashlib
import hmac
import threading
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
        stats=None,
    ) -> None:
        self._lock = threading.Lock()
        self._opening_positions = set()
        self.stats = stats
        self.api_key = api_key
        self.api_secret = api_secret
        self._take_profit = take_profit
        self._stop_loss = stop_loss
        self._leverage = leverage
        self._max_allowed_positions = max_allowed_positions
        self._usdt_quantity = usdt_quantity
        self.use_demo = use_demo

        self.base_url = "https://open-api-vst.bingx.com" if use_demo else "https://open-api.bingx.com"

        self.exchange = ccxt.bingx({
            'apiKey': api_key,
            'secret': api_secret,
            'options': {'defaultType': 'swap'},
        })
        if use_demo:
            self.exchange.set_sandbox_mode(True)

        self._exchange_info = BingxExchangeInfo()
        self._exchange_info.start()

        self._balance_cache = None
        self._balance_cache_time = 0
        self._balance_cache_ttl = 60
        self._positions_cache = None
        self._positions_cache_time = 0
        self._positions_cache_ttl = 10
        self._leverage_cache = {}

    def _sign_request(self, params: dict) -> str:
        query_string = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
        return hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

    def _get_balance_via_api(self) -> float:
        endpoint = "/openApi/swap/v3/user/balance"
        params = {
            "timestamp": int(time.time() * 1000),
            "recvWindow": 10000,
        }
        sorted_keys = sorted(params.keys())
        query_string = "&".join([f"{k}={params[k]}" for k in sorted_keys])
        signature = self._sign_request({k: params[k] for k in sorted_keys})
        url = f"{self.base_url}{endpoint}?{query_string}&signature={signature}"
        headers = {"X-BX-APIKEY": self.api_key}

        try:
            response = requests.get(url, headers=headers)
            data = response.json()
            if data.get("code") != 0:
                logger.error(f"Balance API error: {data}")
                return 0.0
            for asset in data.get("data", []):
                if asset.get("asset") in ("USDT", "VST"):
                    return float(asset.get("balance", 0.0))
            return 0.0
        except Exception as e:
            logger.error(f"Ошибка при получении баланса: {e}")
            return 0.0

    def _get_balance(self) -> float:
        now = time.time()
        if self._balance_cache is not None and (now - self._balance_cache_time) < self._balance_cache_ttl:
            return self._balance_cache
        free = self._get_balance_via_api()
        self._balance_cache = free
        self._balance_cache_time = now
        return free

    def _get_positions(self, use_cache=True) -> list[dict]:
        now = time.time()
        if use_cache and self._positions_cache is not None and (
                now - self._positions_cache_time) < self._positions_cache_ttl:
            return self._positions_cache

        positions = []  # <-- добавляем эту строку
        endpoint = "/openApi/swap/v2/user/positions"
        params = {
            "timestamp": int(time.time() * 1000),
            "recvWindow": 10000,
        }
        sorted_keys = sorted(params.keys())
        query_string = "&".join([f"{k}={params[k]}" for k in sorted_keys])
        signature = self._sign_request({k: params[k] for k in sorted_keys})
        url = f"{self.base_url}{endpoint}?{query_string}&signature={signature}"
        headers = {"X-BX-APIKEY": self.api_key}

        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = requests.get(url, headers=headers)
                data = response.json()
                if data.get("code") != 0:
                    raise Exception(f"Bingx API error: {data}")
                positions = data.get("data", [])
                self._positions_cache = [
                    {
                        "symbol": p["symbol"].replace("-", ""),
                        "side": p.get("positionSide", "").lower(),
                        "entry_price": float(p.get("avgPrice", 0)),
                        "quantity": float(p.get("positionAmt", 0)),
                        "tp_price": 0.0,
                        "sl_price": 0.0,
                        "leverage": int(p.get("leverage", config.LEVERAGE or 1)),
                    }
                    for p in positions if float(p.get("positionAmt", 0)) > 0
                ]
                self._positions_cache_time = now
                return self._positions_cache
            except Exception as e:
                if "100410" in str(e):
                    wait = 2 ** attempt
                    logger.warning(f"Rate limit hit while fetching positions, retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    logger.error(f"Error fetching positions: {e}")
                    raise
        logger.error("Failed to fetch positions after retries")
        return []

    def _set_leverage(self, symbol_clean: str) -> None:
        if not self._leverage:
            return
        symbol_original = self._exchange_info.get_original_symbol(symbol_clean)
        if symbol_original in self._leverage_cache and self._leverage_cache[symbol_original] == self._leverage:
            return

        max_retries = 3
        for attempt in range(max_retries):
            try:
                self.exchange.set_leverage(self._leverage, symbol_original, {'side': 'LONG'})
                self._leverage_cache[symbol_original] = self._leverage
                logger.info(f"Плечо на {symbol_original} установлено на {self._leverage}X")
                return
            except Exception as e:
                if "100410" in str(e):
                    wait = 2 ** attempt
                    logger.warning(f"Rate limit (100410) while setting leverage, retrying in {wait}s...")
                    time.sleep(wait)
                else:
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
        entry_price: float,
    ) -> None:
        with self._lock:
            positions = self._get_positions(use_cache=False)
            if self._max_allowed_positions is not None and len(positions) >= self._max_allowed_positions:
                logger.warning(f"Превышен лимит позиций ({self._max_allowed_positions}) перед отправкой ордера, отмена")
                self._opening_positions.discard(symbol_clean)
                return

        symbol_original = self._exchange_info.get_original_symbol(symbol_clean)
        endpoint = "/openApi/swap/v2/trade/order"

        params = {
            "symbol": symbol_original,
            "side": side.value.upper(),
            "positionSide": "LONG" if side == SignalSide.BUY else "SHORT",
            "type": "MARKET",
            "quantity": quantity,
            "recvWindow": 10000,
            "timestamp": int(time.time() * 1000),
        }

        if take_profit is not None:
            params["takeProfit"] = json.dumps({
                "type": "TAKE_PROFIT_MARKET",
                "stopPrice": take_profit,
                "price": take_profit,
                "workingType": "MARK_PRICE",
                "reduceOnly": True,
            })
        if stop_loss is not None:
            params["stopLoss"] = json.dumps({
                "type": "STOP_MARKET",
                "stopPrice": stop_loss,
                "price": stop_loss,
                "workingType": "MARK_PRICE",
                "reduceOnly": True,
            })

        logger.debug(f"Params before signature: {params}")

        sorted_keys = sorted(params.keys())
        query_string = "&".join([f"{k}={params[k]}" for k in sorted_keys])
        signature = self._sign_request({k: params[k] for k in sorted_keys})
        url = f"{self.base_url}{endpoint}?{query_string}&signature={signature}"
        headers = {"X-BX-APIKEY": self.api_key}

        logger.debug(f"Request URL: {url}")
        logger.debug(f"Request params: {params}")

        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = requests.post(url, headers=headers)
                data = response.json()
                logger.debug(f"Response data: {data}")
                if data.get("code") != 0:
                    if data.get("code") == 109400 and attempt < max_retries - 1:
                        wait = 60
                        logger.warning(f"API временно отключён (109400), повторная попытка через {wait} сек...")
                        time.sleep(wait)
                        continue
                    if data.get("code") == 100421:
                        logger.warning(
                            f"[{symbol_clean}:{side}] Пара временно недоступна для торговли (100421), пропускаем")
                        return
                    raise Exception(f"Bingx API error: {data}")
                order_data = data.get("data", {}).get("order", {})
                logger.info(
                    f"[{symbol_clean}:{side}] Ордер {order_data.get('orderId')} исполнен: "
                    f"цена={float(order_data.get('avgPrice', 0)):.5f}, кол-во={float(order_data.get('executedQty', 0)):.5f}"
                )
                if self.stats:
                    balance = self._get_balance()
                    self.stats.record_open(
                        symbol=symbol_clean,
                        side=side.value,
                        entry_price=entry_price,
                        quantity=quantity,
                        tp_price=take_profit,
                        sl_price=stop_loss,
                        balance=balance,
                        leverage=self._leverage or 0,
                    )
                    self.check_closed_positions()
                break
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                logger.warning(f"Ошибка при создании ордера (попытка {attempt+1}/{max_retries}): {e}")
                time.sleep(10)
            finally:
                with self._lock:
                    self._opening_positions.discard(symbol_clean)

    def get_balance(self) -> float:
        return self._get_balance()

    def check_closed_positions(self):
        if not self.stats:
            return
        logger.debug("Проверка закрытых позиций...")
        try:
            positions = self._get_positions(use_cache=False)
        except Exception as e:
            logger.error(f"Ошибка при получении позиций для статистики: {e}")
            return
        logger.debug(f"Текущие позиции: {[(p['symbol'], p['side']) for p in positions]}")
        logger.debug(f"Открытые сделки в статистике: {list(self.stats.open_trades.keys())}")
        current_keys = {(p["symbol"], p["side"]) for p in positions}
        now = time.time()

        for (symbol, side), trade in list(self.stats.open_trades.items()):
            pos_side = "long" if side == "BUY" else "short"
            if (symbol, pos_side) not in current_keys:
                time_open = trade.open_time.timestamp()
                if now - time_open < 30:
                    continue
                try:
                    original_symbol = self._exchange_info.get_original_symbol(symbol)
                    ticker = self.exchange.fetch_ticker(original_symbol)
                    exit_price = ticker['last']
                except Exception as e:
                    logger.error(f"Не удалось получить цену для {symbol}: {e}")
                    continue
                balance = self._get_balance()
                self.stats.record_close(symbol, side, exit_price, balance)

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
        if config.USE_PERCENT_OF_BALANCE:
            balance = self._get_balance()
            if balance > 0:
                nominal = balance * (config.RISK_PERCENT / 100.0)
            else:
                nominal = self._usdt_quantity
        else:
            nominal = self._usdt_quantity
            # Проверка лимита номинала
        if nominal > config.MAX_POSITION_NOMINAL:
            logger.warning(f"Номинал {nominal:.2f} USDT превышает лимит {config.MAX_POSITION_NOMINAL}, уменьшаем")
            nominal = config.MAX_POSITION_NOMINAL

        qty = nominal / last_price
        return self._exchange_info.round_quantity(symbol, qty)

    def _check_positions_status(self, symbol: str) -> bool:
        with self._lock:
            positions = self._get_positions(use_cache=True)
            if self._max_allowed_positions is not None and len(positions) >= self._max_allowed_positions:
                return False
            if any(p["symbol"] == symbol for p in positions):
                return False
            if symbol in self._opening_positions:
                return False
            self._opening_positions.add(symbol)
            return True

    def process_signal(self, signal: SignalDTO) -> None:
        repr = f"[{signal.symbol}:{signal.side}]"  # <-- эта строка должна быть первой
        try:
            logger.info(f"{repr} Начинаю обработку сигнала")

            clean_symbol = signal.symbol.replace("-", "")
            if clean_symbol not in self._exchange_info.original_symbols:
                logger.warning(f"{repr} Символ не найден в списке Bingx, пропускаем")
                return

            if not self._check_positions_status(clean_symbol):
                logger.info(f"{repr} Нельзя открыть позицию (лимит или уже открыта)")
                return

            if self.CATEGORY == "linear":
                self._set_leverage(clean_symbol)

            quantity = self._calculate_quantity(clean_symbol, signal.last_price)
            stop_loss = self._calculate_sl_price(clean_symbol, signal.last_price, signal.side)
            take_profit = self._calculate_tp_price(clean_symbol, signal.last_price, signal.side)

            logger.info(f"{repr} Расчётные значения: SL={stop_loss:.5f}, TP={take_profit:.5f}")

            self._place_market_order(
                symbol_clean=clean_symbol,
                quantity=quantity,
                side=signal.side,
                stop_loss=stop_loss,
                take_profit=take_profit,
                entry_price=signal.last_price,
            )
        except Exception as e:
            logger.exception(f"{repr} Ошибка при обработке сигнала: {e}")
        finally:
            with self._lock:
                self._opening_positions.discard(clean_symbol)
            logger.info(f"{repr} Завершил обработку сигнала")