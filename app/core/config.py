"""
Конфигурационный файл бота.
Здесь задаются все настройки: тип скринера, биржа, параметры торговли, логирование и статистика.
"""

__all__ = ["config"]

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from app.schemas.enums import ScreenerType, SignalSide, TradebotType

load_dotenv()


@dataclass(frozen=True)
class Configuration:
    # ==================== ОБЩИЕ НАСТРОЙКИ ====================
    USE_DEMO: bool = os.getenv("USE_DEMO", "true").lower() == "true"
    SCREENER_TYPE: ScreenerType = ScreenerType.EMA
    TRADEBOT_TYPE: TradebotType = TradebotType.BINGX_FUTURES
    ALLOWED_SIDES: list[SignalSide] = field(
        default_factory=lambda: [SignalSide.BUY, SignalSide.SELL]
    )

    # ==================== НАСТРОЙКИ РИСК-МЕНЕДЖМЕНТА ====================
    STOP_LOSS: float | None = 0.5
    TAKE_PROFIT: float | None = 1.2
    LEVERAGE: int | None = 10
    USDT_QUANTITY: float = 500
    MAX_ALLOWED_POSITIONS: int = 10
    MAX_POSITION_NOMINAL: float = 5000.0
    MAX_SYMBOLS: int = 500

    # ==================== ФИЛЬТРЫ СКРИНЕРА ====================
    # Фильтр объёма
    USE_VOLUME_FILTER: bool = True
    VOLUME_MULTIPLIER: float = 1.2 # было 1.5
    VOLUME_PERIOD: int = 10

    # Фильтр ATR (отсеивание боковика)
    USE_ATR_FILTER: bool = True
    ATR_THRESHOLD: float = 0.0003    # было 0,001

    # Фильтр минимального движения
    MIN_PRICE_MOVE_PERCENT: float = 0.15 # было 0,3

    # Фильтр ADX (сила тренда)
    USE_ADX_FILTER: bool = False
    ADX_THRESHOLD: int = 25
    ADX_PERIOD: int = 14

    # Дополнительные фильтры (в разработке)
    USE_SUPPORT_RESISTANCE: bool = False
    USE_RSI_DIVERGENCE: bool = False
    USE_CANDLE_PATTERNS: bool = False

    # ========== ФИЛЬТРЫ EMA ==========
    USE_EMA_SPREAD_FILTER: bool = True  # включить фильтр спреда
    MIN_EMA_SPREAD_PERCENT: float = 0.08  # минимум 0.15% расхождения

    # ==================== НАСТРОЙКИ RSI ====================
    RSI_SCREENER_LENGTH: int = 9
    RSI_SCREENER_TIMEFRAME: int = 5
    RSI_SCREENER_LOWER_THRESHOLD: float = 20.0
    RSI_SCREENER_UPPER_THRESHOLD: float = 80.0

    # ==================== НАСТРОЙКИ EMA ====================
    EMA_SCREENER_SHORT_PERIOD: int = 9
    EMA_SCREENER_LONG_PERIOD: int = 21
    EMA_SCREENER_TREND_PERIOD: int = 99
    EMA_SCREENER_TIMEFRAME: int = 3

    # ==================== НАСТРОЙКИ MACD ====================
    MACD_FAST_PERIOD: int = 12
    MACD_SLOW_PERIOD: int = 26
    MACD_SIGNAL_PERIOD: int = 9

    # ==================== ПОДТВЕРЖДЕНИЕ RSI ====================
    USE_RSI_CONFIRMATION: bool = True
    RSI_CONFIRMATION_PERIOD: int = 14
    RSI_CONFIRMATION_THRESHOLD: float = 50.0 # было 55

    # ==================== КЛЮЧИ API ====================
    BYBIT_API_KEY: str = os.getenv("API_KEY", "")
    BYBIT_API_SECRET: str = os.getenv("API_SECRET", "")
    BINGX_API_KEY: str = os.getenv("BINGX_API_KEY", "")
    BINGX_API_SECRET: str = os.getenv("BINGX_API_SECRET", "")

    # ==================== НАСТРОЙКИ ЛОГИРОВАНИЯ ====================
    LOG_STDOUT_LEVEL: Literal["ERROR", "INFO", "DEBUG", "TRACE"] = "INFO"
    LOG_FILE_LEVELS: list[Literal["ERROR", "INFO", "DEBUG", "TRACE"]] | None = None
    LOG_FOLDER_PATH: Path = Path("logs")
    LOG_API_DETAILS: bool = False

    # ==================== СТАТИСТИКА ====================
    STATS_ENABLED: bool = True
    STATS_CSV_PATH: str = "trades.csv"

    # ==================== РАЗМЕР ПОЗИЦИИ ====================
    USE_PERCENT_OF_BALANCE: bool = False
    RISK_PERCENT: float = 1.5

    # ==================== ИНВЕРСИЯ СИГНАЛОВ ====================
    INVERT_SIGNALS: bool = False


config: Configuration = Configuration()