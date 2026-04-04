__all__ = ["BingxExchangeInfo"]

import time
import requests
import threading
from collections import deque
from app.core import config, logger
from .abstract import ABCExchangeInfo


class BingxExchangeInfo(ABCExchangeInfo):
    symbols_data = {}
    original_symbols = {}

    _rate_limit_queue = deque(maxlen=5)  # храним временные метки последних 5 запросов
    _rate_limit_lock = threading.Lock()
    # Очередь для отслеживания времени последних запросов
    _request_times = deque(maxlen=500)

    @classmethod
    def _get_base_url(cls) -> str:
        if config.USE_DEMO:
            return "https://open-api-vst.bingx.com"
        return "https://open-api.bingx.com"

    @classmethod
    def _wait_for_rate_limit(cls):
        """Ждёт, если за последние 900 секунд было 5 запросов."""
        with cls._rate_limit_lock:
            now = time.time()
            # Удаляем записи старше 15 минут (900 сек)
            while cls._rate_limit_queue and now - cls._rate_limit_queue[0] > 900:
                cls._rate_limit_queue.popleft()
            if len(cls._rate_limit_queue) >= 5:
                wait_time = 900 - (now - cls._rate_limit_queue[0]) + 1
                logger.warning(f"Rate limit reached, waiting {wait_time:.1f}s...")
                time.sleep(wait_time)
            cls._rate_limit_queue.append(now)

    @classmethod
    def run(cls):
        """Фоновый поток для обновления данных о символах (точность, оригинальные имена)."""
        while True:
            try:
                base_url = cls._get_base_url()
                url = f"{base_url}/openApi/swap/v2/quote/contracts"
                response = requests.get(url).json()
                data = response.get("data", [])

                precision_dict = {}
                original_dict = {}
                for item in data:
                    # Пропускаем приостановленные символы (status != 1)
                    if item.get("status") != 1:
                        continue
                    symbol = item.get("symbol")
                    if not symbol:
                        continue
                    symbol_clean = symbol.replace("-", "")
                    tick_size = item.get("pricePrecision")
                    step_size = item.get("quantityPrecision")
                    precision_dict[symbol_clean] = [tick_size, step_size]
                    original_dict[symbol_clean] = symbol

                cls.symbols_data = precision_dict
                cls.original_symbols = original_dict  # { "BTCUSDT": "BTC-USDT" }
                logger.info(f"Обновлены данные по символам Bingx ({'DEMO' if config.USE_DEMO else 'REAL'}), {len(precision_dict)} записей")
            except Exception as error:
                logger.error(f"Ошибка в BingxExchangeInfo: {error}")
            time.sleep(60 * 60)

    @classmethod
    def _rate_limit(cls):
        """Ограничивает частоту запросов до 500 за 10 секунд."""
        now = time.time()
        # Удаляем записи, которые были сделаны более 10 секунд назад
        while cls._request_times and now - cls._request_times[0] > 10:
            cls._request_times.popleft()

        # Если мы уже сделали 500 запросов за последние 10 секунд, засыпаем
        if len(cls._request_times) >= 500:
            sleep_time = 10 - (now - cls._request_times[0]) + 0.1
            logger.warning(f"Rate limit почти достигнут (500/10s). Пауза на {sleep_time:.2f} сек.")
            time.sleep(sleep_time)
            # После пробуждения рекурсивно проверяем лимит снова
            return cls._rate_limit()

        # Добавляем текущий запрос в очередь
        cls._request_times.append(now)

    @classmethod
    def fetch_klines(cls, symbol: str, interval: str, limit: int = 100) -> list[dict]:
        """Получает свечи с BingX с контролем скорости."""
        # Вызываем проверку лимита перед каждым запросом
        cls._rate_limit()
        base_url = cls._get_base_url()
        url = f"{base_url}/openApi/swap/v3/quote/klines"
        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        }

        time.sleep(0.5)

        try:
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()
            if data.get("code") != 0:
                logger.error(f"Ошибка получения свечей {symbol}: {data}")
                return []
            klines_raw = data.get("data", [])
            klines = []
            for k in reversed(klines_raw):
                klines.append({
                    't': int(k['time']),
                    'o': float(k['open']),
                    'h': float(k['high']),
                    'l': float(k['low']),
                    'c': float(k['close']),
                    'v': float(k.get('volume', 0)),
                })
            return klines
        except Exception as e:
            logger.error(f"Ошибка при запросе свечей {symbol}: {e}")
            return []

    @classmethod
    def round_price(cls, symbol: str, price: float) -> float:
        assert symbol in cls.symbols_data, f"Symbol {symbol} not found in Bingx symbols_data"
        decimals = cls.symbols_data[symbol.upper()][0]
        return round(price, decimals)

    @classmethod
    def round_quantity(cls, symbol: str, quantity: float) -> float:
        assert symbol in cls.symbols_data, f"Symbol {symbol} not found in Bingx symbols_data"
        decimals = cls.symbols_data[symbol.upper()][1]
        return round(quantity, decimals)

    @classmethod
    def get_original_symbol(cls, clean_symbol: str) -> str:
        original = cls.original_symbols.get(clean_symbol.upper(), clean_symbol)
        if original == clean_symbol:
            logger.warning(f"Symbol {clean_symbol} not found in original_symbols, using as is")
        return original