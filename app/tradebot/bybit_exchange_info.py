__all__ = ["BybitExchangeInfo"]

import re
import time

import requests

from app.core import logger

from .abstract import ABCExchangeInfo


class BybitExchangeInfo(ABCExchangeInfo):
    """Thread what update symbols decimals"""

    symbols_data = dict()

    @classmethod
    def run(cls):
        """Update symbols decimals.
        data variable example:

        "[
            {
                "symbol": "BTCUSDT",
                "contractType": "LinearPerpetual",
                "status": "Trading",
                "baseCoin": "BTC",
                "quoteCoin": "USDT",
                "launchTime": "1585526400000",
                "deliveryTime": "0",
                "deliveryFeeRate": "",
                "priceScale": "2",
                "leverageFilter": {
                    "minLeverage": "1",
                    "maxLeverage": "100.00",
                    "leverageStep": "0.01"
                },
                "priceFilter": {
                    "minPrice": "0.10",
                    "maxPrice": "199999.80",
                    "tickSize": "0.10"
                },
                "lotSizeFilter": {
                    "maxOrderQty": "100.000",
                    "maxMktOrderQty": "100.000",
                    "minOrderQty": "0.001",
                    "qtyStep": "0.001",
                    "postOnlyMaxOrderQty": "1000.000",
                    "minNotionalValue": "5"
                },
                "unifiedMarginTrade": true,
                "fundingInterval": 480,
                "settleCoin": "USDT",
                "copyTrading": "both",
                "upperFundingRate": "0.00375",
                "lowerFundingRate": "-0.00375"
            }
        ],
        """
        while True:
            try:
                precision_dict = dict()
                url: str = "https://api.bybit.com/v5/market/instruments-info?category=linear"
                data: list[dict] = requests.get(url).json()["result"]["list"]
                for el in data:
                    tick_size = el["priceFilter"]["tickSize"]
                    step_size = el["lotSizeFilter"]["qtyStep"]

                    tick_size = list(re.sub("0+$", "", tick_size))
                    if len(tick_size) == 1:
                        tick_size = 1
                    else:
                        tick_size = len(tick_size) - 2

                    step_size = list(re.sub("0+$", "", step_size))
                    if len(step_size) == 1:
                        step_size = 0
                    else:
                        step_size = len(step_size) - 2

                    precision_dict[el["symbol"]] = [tick_size, step_size]

                cls.symbols_data = precision_dict

            except Exception as error:
                logger.error(f"{type(error)} in _update_data in symbols_decimals worker: {error}.")
            time.sleep(60 * 60)

    @classmethod
    def round_price(cls, symbol: str, price: float) -> float:
        """
        Rounds price for ticker
        :param symbol: ticker from binance.com, like "BTCUSDT" or "xrpusdt"
        :param price: any float
        :return: round price for ticker
        """
        assert symbol in cls.symbols_data, "Symbol not in symbols_data in SymbolsDecimals object"

        return round(price, cls.symbols_data[symbol.upper()][0])

    @classmethod
    def round_quantity(cls, symbol: str, quantity: float) -> float:
        """
        Rounds qty for ticker
        :param symbol: ticker from binance.com, like "BTCUSDT" or "xrpusdt"
        :param quantity: any float
        :return: rounded qty for ticker
        """
        assert symbol in cls.symbols_data, "Symbol not in symbols_data in SymbolsDecimals object"

        return abs(round(quantity, cls.symbols_data[symbol.upper()][1]))
