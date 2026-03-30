import threading
import time
from threading import Thread

from app.core import config, logger
from app.schemas import SignalDTO
from app.screener import SCREENER_MAPPER, ABCScreener
from app.screener.ema import EMAScreener
from app.screener.rsi import RSIScreener
from app.tradebot import TRADEBOT_MAPPER, ABCTradebot
from app.schemas.enums import TradebotType, ScreenerType, SignalSide
from app.stats.collector import StatsCollector


class Manager:
    def __init__(self) -> None:
        # Статистика (если включена)
        self.stats = StatsCollector() if config.STATS_ENABLED else None

        # Инициализация скринера с параметрами в зависимости от типа
        screener_type = config.SCREENER_TYPE
        if screener_type == ScreenerType.EMA:
            self._screener: ABCScreener = EMAScreener(
                callback=self._signal_callback,
                short_period=config.EMA_SCREENER_SHORT_PERIOD,
                long_period=config.EMA_SCREENER_LONG_PERIOD,
                timeframe=config.EMA_SCREENER_TIMEFRAME,
            )
        elif screener_type == ScreenerType.RSI:
            self._screener = RSIScreener(
                callback=self._signal_callback,
            )
        else:
            self._screener = SCREENER_MAPPER[screener_type](
                callback=self._signal_callback
            )

        # Определяем тип трейдбота и выбираем ключи
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

        # Инициализация трейдбота (передаём stats)
        self._tradebot: ABCTradebot = TRADEBOT_MAPPER[tradebot_type](
            api_key=api_key,
            api_secret=api_secret,
            use_demo=use_demo,
            stats=self.stats,
        )

        # Синхронизация открытых позиций со статистикой (если включена)
        if self.stats and hasattr(self._tradebot, '_get_positions'):
            self.stats.sync_open_trades_from_exchange(self._tradebot)

        # Вывод начального баланса (если статистика включена и есть метод get_balance)
        if self.stats and hasattr(self._tradebot, 'get_balance'):
            balance = self._tradebot.get_balance()
            logger.info(f"Начальный баланс: {balance:.2f} USDT")

        # Вывод информации о режиме инверсии
        if config.INVERT_SIGNALS:
            logger.info("🔄 РЕЖИМ ИНВЕРСИИ ВКЛЮЧЁН: все сигналы будут открываться в противоположную сторону")
        else:
            logger.info("✅ РЕЖИМ ИНВЕРСИИ ОТКЛЮЧЁН (торгуем по сигналам скринера)")

        # Вывод начальной статистики (если есть завершённые сделки)
        if self.stats and self.stats.trades:
            logger.info("📊 Статистика предыдущих сессий:")
            self.stats.print_summary()

    def run(self) -> None:
        """Метод для запуска менеджера."""
        # Запускаем поток для обработки команд (если статистика включена)
        if self.stats:
            logger.info("🖥️ Запущен поток обработки команд. Введите 'stats' для просмотра статистики.")
            cmd_thread = threading.Thread(target=self._command_loop, daemon=True)
            cmd_thread.start()

        # Запускаем скринер (блокирующий)
        self._screener.run()

        # Сюда мы никогда не дойдём, потому что скринер бесконечен,
        # но оставим для обработки прерываний
        try:
            while True:
                time.sleep(1)
                if self.stats and hasattr(self._tradebot, 'check_closed_positions'):
                    self._tradebot.check_closed_positions()
                time.sleep(4)
        except KeyboardInterrupt:
            logger.info("Получен сигнал остановки, завершаем работу...")
            if self.stats:
                self.stats.print_summary()

    def _command_loop(self):
        print("\n" + "="*50)
        print("Доступные команды: stats, stats time, reset stats, balance, exit")
        print("="*50 + "\n", flush=True)
        while True:
            try:
                cmd = input().strip().lower()
                if cmd == 'stats':
                    if self.stats:
                        self.stats.print_summary()
                    else:
                        print("Статистика отключена (STATS_ENABLED = False)")
                elif cmd == 'stats time':
                    if self.stats:
                        self.stats.print_time_breakdown()
                    else:
                        print("Статистика отключена")
                elif cmd == 'reset stats':
                    if self.stats:
                        self.stats.reset()
                        if hasattr(self._tradebot, '_get_positions'):
                            self.stats.sync_open_trades_from_exchange(self._tradebot)
                    else:
                        print("Статистика отключена")
                elif cmd == 'balance':
                    if hasattr(self._tradebot, 'get_balance'):
                        balance = self._tradebot.get_balance()
                        print(f"💰 Доступный баланс USDT: {balance:.2f}")
                    else:
                        print("Метод get_balance не поддерживается")
                elif cmd == 'exit':
                    break
            except (EOFError, KeyboardInterrupt):
                break

    def _signal_callback(self, signal: SignalDTO) -> None:
        # Инвертируем сигнал, если включено в конфиге
        if config.INVERT_SIGNALS:
            signal.side = SignalSide.BUY if signal.side == SignalSide.SELL else SignalSide.SELL
            logger.debug(f"Сигнал инвертирован: {signal.symbol} {signal.side}")
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