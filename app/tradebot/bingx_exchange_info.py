__all__ = ["BingxExchangeInfo"]

import time
import requests

from app.core import config, logger
from .abstract import ABCExchangeInfo


class BingxExchangeInfo(ABCExchangeInfo):
    symbols_data = {}
    original_symbols = {}

    @classmethod
    def _get_base_url(cls) -> str:
        if config.USE_DEMO:
            return "https://open-api-vst.bingx.com"
        return "https://open-api.bingx.com"

    @classmethod
    def run(cls):
        while True:
            try:
                base_url = cls._get_base_url()
                url = f"{base_url}/openApi/swap/v2/quote/contracts"
                response = requests.get(url).json()
                data = response.get("data", [])

                precision_dict = {}
                original_dict = {}
                for item in data:
                    symbol = item.get("symbol")
                    if not symbol:
                        continue
                    symbol_clean = symbol.replace("-", "")
                    tick_size = item.get("pricePrecision")
                    step_size = item.get("quantityPrecision")
                    precision_dict[symbol_clean] = [tick_size, step_size]
                    original_dict[symbol_clean] = symbol

                cls.symbols_data = precision_dict
                cls.original_symbols = original_dict
                logger.info(f"Обновлены данные по символам Bingx ({'DEMO' if config.USE_DEMO else 'REAL'}), {len(precision_dict)} записей")
            except Exception as error:
                logger.error(f"Ошибка в BingxExchangeInfo: {error}")
            time.sleep(60 * 60)

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