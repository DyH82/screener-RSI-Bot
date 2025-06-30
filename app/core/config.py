"""
Конфигурационные данные и настройка логирования.
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
    """Общий класс конфигурации."""

    # === Общие настройки ===

    SCREENER_TYPE: ScreenerType = ScreenerType.RSI
    """Тип скринера для торговли."""

    TRADEBOT_TYPE: TradebotType = TradebotType.BYBIT_FUTURES
    """Тип торгового бота."""

    ALLOWED_SIDES: list[SignalSide] = field(
        default_factory=lambda: [SignalSide.BUY, SignalSide.SELL]
    )
    """Стороны, на которые бот может торговать."""

    STOP_LOSS: float | None = 1
    """Размер стоп-лосса для торговли в %. Можно поставить 0 или None чтобы отключить стоп-лосс."""

    TAKE_PROFIT: float | None = 2
    """Размер тейк-профита для торговли в %. Можно поставить 0 или None чтобы отключить тейк-профит."""

    LEVERAGE: int | None = 10
    """Торговое плечо для торговли. Можно поставить 0 или None чтобы отключить изменение плеча при обработке сигнала."""

    USDT_QUANTITY: float = 100
    """Размер позиции в USDT. Это КОНЕЧНЫЙ размер позиции после плеча, т.е. маржа будет меньше, в зависимости от плеча."""

    MAX_ALLOWED_POSITIONS: int = 4
    """Максимальное количество открытых позиций одновременно."""

    # === Настройки скринера RSI ===

    RSI_SCREENER_LENGTH: int = 14
    """Длина периода для скринера RSI."""

    RSI_SCREENER_TIMEFRAME: int = 1
    """Временной интервал для скринера RSI.
    Доступные интервалы для Bybit Klines Websocket: 1 3 5 15 30 60 120 240 360 720 (min)
    """

    RSI_SCREENER_LOWER_THRESHOLD: float = 20.0
    """Нижний порог для скринера RSI."""

    RSI_SCREENER_UPPER_THRESHOLD: float = 80.0
    """Верхний порог для скринера RSI."""

    # === Настройки торговли на Bybit через API ===

    BYBIT_API_KEY: str = os.getenv("API_KEY", "")
    """Ключ для торговли на Bybit через API."""

    BYBIT_API_SECRET: str = os.getenv("API_SECRET", "")
    """Секретный ключ для торговли на Bybit через API."""

    # === Настройки логирования ===

    LOG_STDOUT_LEVEL: Literal["ERROR", "INFO", "DEBUG", "TRACE"] = "INFO"
    """Уровень логирования для вывода в консоль."""

    LOG_FILE_LEVELS: list[Literal["ERROR", "INFO", "DEBUG", "TRACE"]] | None = None
    """Уровни для вывода в файл. По умолчанию: ["ERROR", "INFO", "DEBUG"]."""

    LOG_FOLDER_PATH: Path = Path("logs")
    """Базовая директория для файлов логов."""


config: Configuration = Configuration()
