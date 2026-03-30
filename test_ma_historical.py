"""
Поиск всех пересечений SMA5/10 за последние N свечей на BingX.
"""

import requests
import time
from datetime import datetime, timedelta

SYMBOL = "SHAPE-USDT"
TIMEFRAME = "1m"
LIMIT = 120  # сколько свечей запросить (120 = 2 часа)
USE_DEMO = True

BASE_URL = "https://open-api-vst.bingx.com" if USE_DEMO else "https://open-api.bingx.com"

def fetch_klines(symbol, interval, limit):
    url = f"{BASE_URL}/openApi/swap/v2/quote/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        if data.get("code") != 0:
            print(f"Ошибка API: {data}")
            return []
        klines_raw = data.get("data", [])
        # Преобразуем и переворачиваем (от старых к новым)
        klines = []
        for k in reversed(klines_raw):
            klines.append({
                'timestamp': int(k['time']),
                'close': float(k['close']),
            })
        return klines
    except Exception as e:
        print(f"Ошибка запроса: {e}")
        return []

def calculate_sma(klines, period):
    if len(klines) < period:
        return None
    closes = [k['close'] for k in klines[-period:]]
    return sum(closes) / period

def main():
    print(f"Загружаем {LIMIT} свечей {SYMBOL} {TIMEFRAME}...")
    klines = fetch_klines(SYMBOL, TIMEFRAME, LIMIT)
    if not klines:
        print("Не удалось получить данные")
        return

    print(f"Получено свечей: {len(klines)}")
    if len(klines) < 10:
        print("Недостаточно данных")
        return

    prev_ma5 = None
    prev_ma10 = None
    crossings = []

    for i in range(9, len(klines)):
        # Используем данные до текущего индекса
        sub = klines[:i+1]
        ma5 = calculate_sma(sub, 5)
        ma10 = calculate_sma(sub, 10)
        if ma5 is None or ma10 is None:
            continue
        if prev_ma5 is not None and prev_ma10 is not None:
            if prev_ma5 < prev_ma10 and ma5 > ma10:
                crossings.append((i, 'BUY', klines[i]['timestamp']))
            elif prev_ma5 > prev_ma10 and ma5 < ma10:
                crossings.append((i, 'SELL', klines[i]['timestamp']))
        prev_ma5, prev_ma10 = ma5, ma10

    if not crossings:
        print("Пересечений не найдено.")
    else:
        print("\nНайденные пересечения (время свечи):")
        for idx, typ, ts in crossings:
            dt = datetime.fromtimestamp(ts/1000).strftime('%Y-%m-%d %H:%M:%S')
            print(f"{dt} {typ}")

if __name__ == "__main__":
    main()