from threading import Event, Thread

from app.core import config, logger
from app.schemas import SignalDTO
from app.screener import SCREENER_MAPPER, ABCScreener
from app.tradebot import TRADEBOT_MAPPER, ABCTradebot


class Manager:
    """Менеджер для связи скринера и клиента для выставления ордеров."""

    def __init__(self) -> None:
        self._screener: ABCScreener = SCREENER_MAPPER[config.SCREENER_TYPE](
            callback=self._signal_callback
        )
        self._tradebot: ABCTradebot = TRADEBOT_MAPPER[config.TRADEBOT_TYPE](
            api_key=config.BYBIT_API_KEY, api_secret=config.BYBIT_API_SECRET
        )

    def run(self) -> None:
        """Метод для запуска менеджера."""
        # Запускаем скринер
        self._screener.run()

        # Не даем программе завершиться с помощью бесконечной заморозки
        Event().wait()

    def _signal_callback(self, signal: SignalDTO) -> None:
        """Обработчик сигнала от скринера."""
        logger.success(
            f"Получен сигнал: {signal.symbol} {signal.side} {signal.prev_rsi} -> {signal.curr_rsi}"
        )
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
