# """
# Мультивалютный тест на пересечение EMA5/EMA10 на BingX (улучшенный).
# """
#
# import requests
# import time
# import os
# from datetime import datetime
#
# # ========== НАСТРОЙКИ ==========
# SYMBOLS = [
#     "NAORIS-USDT",
#     "SHAPE-USDT",
#     # "SOL-USDT",
#     # "BNB-USDT",
#     # "XRP-USDT",
#     # "DOGE-USDT",
#     # "ADA-USDT",
#     # "AVAX-USDT",
#     # "DOT-USDT",
#     # "LINK-USDT"
# ]
#
# TIMEFRAME = "3m"           # Интервал: 1m, 5m, 15m, 30m, 1h, 4h, 1d
# USE_DEMO = True            # True – демо, False – реальный счёт
# USE_EMA = True             # True – EMA, False – SMA
# SENSITIVITY = 0.0002       # 0.02% порог чувствительности (чтобы избежать микропересечений)
# # ===============================
#
# BASE_URL = "https://open-api-vst.bingx.com" if USE_DEMO else "https://open-api.bingx.com"
#
# def fetch_klines(symbol, interval, limit=150):
#     url = f"{BASE_URL}/openApi/swap/v2/quote/klines"
#     params = {"symbol": symbol, "interval": interval, "limit": limit}
#     try:
#         resp = requests.get(url, params=params, timeout=10)
#         data = resp.json()
#         if data.get("code") != 0:
#             return []
#         klines_raw = data.get("data", [])
#         klines = []
#         for k in klines_raw:
#             klines.append({
#                 'timestamp': int(k['time']),
#                 'close': float(k['close']),
#             })
#         klines.reverse()
#         return klines
#     except Exception as e:
#         return []
#
# def calculate_ema(klines, period):
#     """Расчёт EMA по формуле Wilder (как в RSI-скринере)."""
#     if len(klines) < period:
#         return None
#     closes = [k['close'] for k in klines]
#     k = 2 / (period + 1)
#     ema = sum(closes[:period]) / period
#     for price in closes[period:]:
#         ema = price * k + ema * (1 - k)
#     return ema
#
# def calculate_sma(klines, period):
#     if len(klines) < period:
#         return None
#     closes = [k['close'] for k in klines[-period:]]
#     return sum(closes) / period
#
# def calculate_ma(klines, period):
#     if USE_EMA:
#         return calculate_ema(klines, period)
#     else:
#         return calculate_sma(klines, period)
#
# def clear_screen():
#     os.system('cls' if os.name == 'nt' else 'clear')
#
# def main():
#     print(f"Мультивалютный скрипт запущен. Слежу за {len(SYMBOLS)} монетами...")
#     print(f"Таймфрейм: {TIMEFRAME}, {'EMA' if USE_EMA else 'SMA'}5/10, порог чувствительности: {SENSITIVITY*100:.2f}%")
#     prev_diff = {sym: None for sym in SYMBOLS}
#     try:
#         while True:
#             clear_screen()
#             now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
#             print(f"Обновление: {now} | Таймфрейм: {TIMEFRAME}")
#             print("-" * 90)
#             print(f"{'Символ':<12} {'Цена':<12} {'MA5':<14} {'MA10':<14} {'Разница':<12} {'Сигнал'}")
#             print("-" * 90)
#
#             for symbol in SYMBOLS:
#                 klines = fetch_klines(symbol, TIMEFRAME, limit=100)
#                 if not klines:
#                     print(f"{symbol:<12} {'-':<12} {'-':<14} {'-':<14} {'-':<12} {'Ошибка'}")
#                     continue
#
#                 last_price = klines[-1]['close']
#                 ma5 = calculate_ma(klines, 5)
#                 ma10 = calculate_ma(klines, 10)
#                 if ma5 is None or ma10 is None:
#                     print(f"{symbol:<12} {last_price:<12.5f} {'-':<14} {'-':<14} {'-':<12} {'Недостаточно данных'}")
#                     continue
#
#                 diff = ma5 - ma10
#                 diff_percent = diff / last_price * 100
#                 signal = ""
#                 # Проверяем пересечение с учётом порога чувствительности
#                 if prev_diff[symbol] is not None:
#                     # Сигнал только если разница изменила знак и абсолютное значение новой разницы > порога
#                     if prev_diff[symbol] < 0 and diff > 0 and diff > SENSITIVITY * last_price:
#                         signal = "🔔 BUY"
#                     elif prev_diff[symbol] > 0 and diff < 0 and -diff > SENSITIVITY * last_price:
#                         signal = "🔔 SELL"
#                 prev_diff[symbol] = diff
#
#                 print(f"{symbol:<12} {last_price:<12.5f} {ma5:<14.5f} {ma10:<14.5f} {diff_percent:>+10.4f}% {signal}")
#
#             print("-" * 90)
#             print("Следующее обновление через 65 секунд...")
#             time.sleep(65)   # ждём 65 секунд, чтобы свеча точно закрылась
#     except KeyboardInterrupt:
#         print("\nЗавершено.")
#
# if __name__ == "__main__":
#     main()

"""тест вар2"""
"""
Точное обнаружение пересечений MA5/MA10 на BingX с использованием pandas и pandas_ta.
"""

import requests
import time
import pandas as pd
import pandas_ta as ta
from datetime import datetime

# ========== НАСТРОЙКИ ==========
SYMBOL = "SHAPE-USDT"       # Символ с дефисом
TIMEFRAME = "1m"            # Таймфрейм: 1m, 5m, 15m, 30m, 1h, 4h, 1d
USE_EMA = True             # False – SMA, True – EMA
LIMIT = 50                  # Количество свечей для расчёта
UPDATE_INTERVAL = 60        # Секунд между проверками (лучше 60 для 1m)
USE_DEMO = True             # True – тестнет, False – реальный счёт
# ===============================

BASE_URL = "https://open-api-vst.bingx.com" if USE_DEMO else "https://open-api.bingx.com"

def fetch_klines(symbol, interval, limit):
    """Получает klines с BingX и возвращает DataFrame."""
    url = f"{BASE_URL}/openApi/swap/v2/quote/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        if data.get("code") != 0:
            print(f"Ошибка API: {data}")
            return pd.DataFrame()
        klines_raw = data.get("data", [])
        rows = []
        for k in klines_raw:
            rows.append({
                'timestamp': int(k['time']),
                'open': float(k['open']),
                'high': float(k['high']),
                'low': float(k['low']),
                'close': float(k['close']),
                'volume': float(k.get('volume', 0))
            })
        df = pd.DataFrame(rows)
        # Свечи приходят от новых к старым, переворачиваем
        df = df.iloc[::-1].reset_index(drop=True)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        print(f"Ошибка запроса: {e}")
        return pd.DataFrame()

def calculate_ma(df, period):
    """Добавляет MA (SMA или EMA) в DataFrame."""
    if USE_EMA:
        df[f'MA{period}'] = ta.ema(df['close'], length=period)
    else:
        df[f'MA{period}'] = ta.sma(df['close'], length=period)
    return df

def check_crossover(df):
    """Проверяет пересечение MA5/MA10 на последних двух закрытых свечах."""
    if len(df) < 3:
        return None, None
    # Берём последние две свечи (индексы -2 и -1)
    prev = df.iloc[-2]
    curr = df.iloc[-1]
    # Убедимся, что значения MA не NaN
    if pd.isna(prev['MA5']) or pd.isna(prev['MA10']) or pd.isna(curr['MA5']) or pd.isna(curr['MA10']):
        return None, None
    # Золотой крест (BUY)
    if prev['MA5'] < prev['MA10'] and curr['MA5'] > curr['MA10']:
        return 'BUY', curr['timestamp']
    # Смертельный крест (SELL)
    elif prev['MA5'] > prev['MA10'] and curr['MA5'] < curr['MA10']:
        return 'SELL', curr['timestamp']
    else:
        return None, None

def main():
    print(f"Скрипт запущен. Слежу за {SYMBOL} ({TIMEFRAME}), {'EMA' if USE_EMA else 'SMA'}5/10.")
    prev_signal = None
    try:
        while True:
            df = fetch_klines(SYMBOL, TIMEFRAME, LIMIT)
            if df.empty:
                print("Не удалось получить данные, повтор через 10 сек")
                time.sleep(10)
                continue

            df = calculate_ma(df, 5)
            df = calculate_ma(df, 10)

            # Выводим последние 5 свечей для контроля
            print("\n" + "="*80)
            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} – {SYMBOL} {TIMEFRAME}")
            print(df[['timestamp', 'close', 'MA5', 'MA10']].tail(5).to_string(float_format='%.5f'))

            signal, time_signal = check_crossover(df)
            if signal:
                if signal != prev_signal:
                    print(f"\n🔔 СИГНАЛ: {signal} на свече {time_signal}")
                    prev_signal = signal
                    # Здесь можно добавить звук или запись в лог
                else:
                    print(f"\nСигнал {signal} повторяется (уже был)")
            else:
                print("\nНет пересечения.")

            print(f"Следующее обновление через {UPDATE_INTERVAL} сек...")
            time.sleep(UPDATE_INTERVAL)
    except KeyboardInterrupt:
        print("\nЗавершено.")

if __name__ == "__main__":
    main()