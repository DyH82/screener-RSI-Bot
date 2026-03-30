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
    # Демо-режим (True – тестнет BingX, False – реальный счёт)
    USE_DEMO: bool = os.getenv("USE_DEMO", "true").lower() == "true"

    # Тип скринера: RSI или EMA
    # ScreenerType.RSI  – стандартный RSI с порогами перекупленности/перепроданности
    # ScreenerType.EMA  – пересечение двух экспоненциальных средних (короткой и длинной)
    SCREENER_TYPE: ScreenerType = ScreenerType.RSI

    # Тип трейдбота: BYBIT_FUTURES (Bybit) или BINGX_FUTURES (BingX)
    TRADEBOT_TYPE: TradebotType = TradebotType.BINGX_FUTURES

    # Разрешённые стороны для торговли (можно оставить BUY и SELL)
    ALLOWED_SIDES: list[SignalSide] = field(
        default_factory=lambda: [SignalSide.BUY, SignalSide.SELL]
    )

    # ==================== НАСТРОЙКИ РИСК-МЕНЕДЖМЕНТА ====================
    # Стоп-лосс в процентах от цены входа (None – отключить)
    STOP_LOSS: float | None = 0.5   # 0.5% убытка
    # Тейк-профит в процентах от цены входа (None – отключить)
    TAKE_PROFIT: float | None = 1.5  # 1.5% прибыли

    # Торговое плечо (10 – стандартное, None – не менять)
    LEVERAGE: int | None = 10

    # Фиксированный размер позиции в USDT (используется, если USE_PERCENT_OF_BALANCE = False)
    USDT_QUANTITY: float = 500

    # Максимальное количество одновременно открытых позиций
    MAX_ALLOWED_POSITIONS: int = 10

    # ==================== НАСТРОЙКИ RSI СКРИНЕРА ====================
    # Период RSI (классический – 14, для скальпинга можно 7–9)
    RSI_SCREENER_LENGTH: int = 9
    # Таймфрейм в минутах (1, 5, 15, 30, 60, 120, 240, 360, 720)
    RSI_SCREENER_TIMEFRAME: int = 1
    # Нижний порог перепроданности (сигнал на покупку)
    RSI_SCREENER_LOWER_THRESHOLD: float = 20.0
    # Верхний порог перекупленности (сигнал на продажу)
    RSI_SCREENER_UPPER_THRESHOLD: float = 85.0

    # ==================== НАСТРОЙКИ EMA СКРИНЕРА ====================
    # Короткий период EMA (быстрая средняя)
    EMA_SCREENER_SHORT_PERIOD: int = 9
    # Длинный период EMA (медленная средняя)
    EMA_SCREENER_LONG_PERIOD: int = 21
    # Таймфрейм EMA (минуты)
    EMA_SCREENER_TIMEFRAME: int = 5

    # ==================== КЛЮЧИ API ====================
    # Ключи Bybit (оставлены для совместимости, если не используете Bybit – можно игнорировать)
    BYBIT_API_KEY: str = os.getenv("API_KEY", "")
    BYBIT_API_SECRET: str = os.getenv("API_SECRET", "")
    # Ключи BingX (обязательны для торговли)
    BINGX_API_KEY: str = os.getenv("BINGX_API_KEY", "")
    BINGX_API_SECRET: str = os.getenv("BINGX_API_SECRET", "")

    # ==================== НАСТРОЙКИ ЛОГИРОВАНИЯ ====================
    # Уровень вывода в консоль (ERROR, INFO, DEBUG, TRACE)
    LOG_STDOUT_LEVEL: Literal["ERROR", "INFO", "DEBUG", "TRACE"] = "INFO"
    # Уровни для записи в файл (можно оставить None)
    LOG_FILE_LEVELS: list[Literal["ERROR", "INFO", "DEBUG", "TRACE"]] | None = None
    # Папка для логов
    LOG_FOLDER_PATH: Path = Path("logs")
    # Детальный вывод ответов API (True – полный JSON, False – краткий)
    LOG_API_DETAILS: bool = False

    # ==================== СТАТИСТИКА ====================
    # Включить сбор статистики (True/False)
    STATS_ENABLED: bool = True
    # Путь к CSV-файлу статистики
    STATS_CSV_PATH: str = "trades.csv"

    # ==================== РАЗМЕР ПОЗИЦИИ ====================
    # Использовать процент от баланса (True) или фиксированную сумму (False)
    USE_PERCENT_OF_BALANCE: bool = False
    # Процент от баланса (если USE_PERCENT_OF_BALANCE = True)
    RISK_PERCENT: float = 2.0

    # ==================== ИНВЕРСИЯ СИГНАЛОВ ====================
    # Если True, то сигнал BUY превращается в SELL и наоборот (обратная стратегия)
    INVERT_SIGNALS: bool = False


config: Configuration = Configuration()