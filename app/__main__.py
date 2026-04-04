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

    def print_config_info(self):
        """Выводит текущие настройки из config.py."""
        from app.core import config
        print("\n" + "=" * 60)
        print("📋 ТЕКУЩИЕ НАСТРОЙКИ КОНФИГУРАЦИИ")
        print("=" * 60)
        print(f"🔹 Биржа: {'ДЕМО (тестнет)' if config.USE_DEMO else 'РЕАЛ'}")
        print(f"🔹 Тип трейдбота: {config.TRADEBOT_TYPE.value}")
        print(f"🔹 Скринер: {config.SCREENER_TYPE.value.upper()}")
        print(f"🔹 Режим инверсии: {'ВКЛЮЧЁН' if config.INVERT_SIGNALS else 'ОТКЛЮЧЁН'}")
        print(f"🔹 Макс. символов для сканирования: {config.MAX_SYMBOLS}")

        print("\n📊 УПРАВЛЕНИЕ РИСКАМИ:")
        print(f"   Стоп-лосс: {config.STOP_LOSS}%")
        print(f"   Тейк-профит: {config.TAKE_PROFIT}%")
        print(f"   Плечо: {config.LEVERAGE}x")
        print(f"   Размер позиции: {config.USDT_QUANTITY} USDT")
        print(f"   Макс. позиций: {config.MAX_ALLOWED_POSITIONS}")
        print(
            f"   Процент от баланса: {'ДА' if config.USE_PERCENT_OF_BALANCE else 'НЕТ'} (риск: {config.RISK_PERCENT}%)")

        print("\n📈 НАСТРОЙКИ RSI:")
        print(f"   Период: {config.RSI_SCREENER_LENGTH}")
        print(f"   Таймфрейм: {config.RSI_SCREENER_TIMEFRAME} мин")
        print(f"   Нижний порог: {config.RSI_SCREENER_LOWER_THRESHOLD}")
        print(f"   Верхний порог: {config.RSI_SCREENER_UPPER_THRESHOLD}")

        print("\n📊 НАСТРОЙКИ EMA:")
        print(f"   Короткий период: {config.EMA_SCREENER_SHORT_PERIOD}")
        print(f"   Длинный период: {config.EMA_SCREENER_LONG_PERIOD}")
        print(f"   Таймфрейм: {config.EMA_SCREENER_TIMEFRAME} мин")

        print("\n📊 ПОДТВЕРЖДЕНИЕ СИГНАЛОВ (EMA + RSI):")
        print(f"   Использовать RSI подтверждение: {'ДА' if config.USE_RSI_CONFIRMATION else 'НЕТ'}")
        if config.USE_RSI_CONFIRMATION:
            print(f"   Период RSI: {config.RSI_CONFIRMATION_PERIOD}")
            print(f"   Порог: {config.RSI_CONFIRMATION_THRESHOLD} (выше -> BUY, ниже -> SELL)")

        print("\n🔍 ФИЛЬТРЫ СКРИНЕРА:")
        print(f"   Уровни поддержки/сопротивления: {'✅ ВКЛ' if config.USE_SUPPORT_RESISTANCE else '❌ ВЫКЛ'}")
        print(f"   Дивергенция RSI: {'✅ ВКЛ' if config.USE_RSI_DIVERGENCE else '❌ ВЫКЛ'}")
        print(f"   Свечные паттерны: {'✅ ВКЛ' if config.USE_CANDLE_PATTERNS else '❌ ВЫКЛ'}")
        print(f"   Фильтр объёма: {'✅ ВКЛ' if config.USE_VOLUME_FILTER else '❌ ВЫКЛ'}")
        if config.USE_VOLUME_FILTER:
            print(f"      Множитель: {config.VOLUME_MULTIPLIER}")
            print(f"      Период: {config.VOLUME_PERIOD}")

        print("\n📝 ЛОГИРОВАНИЕ И СТАТИСТИКА:")
        print(f"   Уровень логов: {config.LOG_STDOUT_LEVEL}")
        print(f"   Статистика: {'✅ ВКЛ' if config.STATS_ENABLED else '❌ ВЫКЛ'}")
        print(f"   CSV-файл: {config.STATS_CSV_PATH}")
        print("=" * 60)
    def _command_loop(self):
        print("\n" + "="*50)
        print("Доступные команды: stats, stats time, reset stats, balance, info, exit")
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
                elif cmd == 'info':
                    self.stats.print_config_info()
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