import time
from threading import Thread

from app.core import config, logger
from app.schemas import SignalDTO
from app.screener import SCREENER_MAPPER, ABCScreener
from app.tradebot import TRADEBOT_MAPPER, ABCTradebot
from app.schemas.enums import TradebotType


class Manager:
    def __init__(self) -> None:
        self._screener: ABCScreener = SCREENER_MAPPER[config.SCREENER_TYPE](
            callback=self._signal_callback
        )
        tradebot_type = config.TRADEBOT_TYPE
        if tradebot_type == TradebotType.BYBIT_FUTURES:
            api_key = config.BYBIT_API_KEY
            api_secret = config.BYBIT_API_SECRET
            use_demo = False
        elif tradebot_type == TradebotType.BINGX_FUTURES:
            api_key = config.BINGX_API_KEY
            api_secret = config.BINGX_API_SECRET
            use_demo = config.USE_DEMO
        else:
            raise ValueError(f"Unknown tradebot type: {tradebot_type}")

        self._tradebot: ABCTradebot = TRADEBOT_MAPPER[tradebot_type](
            api_key=api_key,
            api_secret=api_secret,
            use_demo=use_demo,
        )

    def run(self) -> None:
        """Метод для запуска менеджера."""
        self._screener.run()
        try:
            # Бесконечный цикл, чтобы программа не завершалась
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Получен сигнал остановки, завершаем работу...")

    def _signal_callback(self, signal: SignalDTO) -> None:
        """Обработчик сигнала от скринера."""
        if signal.side in config.ALLOWED_SIDES:
            logger.success(f"Получен сигнал: {signal.symbol} {signal.side}")
            Thread(target=self._tradebot.process_signal, args=(signal,), daemon=True).start()


def main() -> None:
    """Точка входа в приложение."""
    Manager().run()


if __name__ == "__main__":
    try:
        logger.success("Приложение запущено")
        main()
    except KeyboardInterrupt:
        logger.info("Остановка приложения пользователем ...")
    except Exception as e:
        logger.exception(f"Глобальная ошибка: {e}")
    finally:
        logger.success("Приложение остановлено")