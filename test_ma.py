"""
Тестовый скрипт для отображения скользящих средних (MA5, MA10, MA30) на BingX.
Обновляется каждую минуту, очищает экран для удобства.
"""

import requests
import time
import os

# ========== НАСТРОЙКИ ==========
SYMBOL = "BTC-USDT"        # Символ с дефисом (как на BingX)
TIMEFRAME = "1m"           # Интервал: 1m, 5m, 15m, 30m, 1h, 4h, 1d
USE_DEMO = True            # True – демо, False – реальный счёт
# ===============================

BASE_URL = "https://open-api-vst.bingx.com" if USE_DEMO else "https://open-api.bingx.com"

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def fetch_klines(symbol, interval, limit=150):
    url = f"{BASE_URL}/openApi/swap/v2/quote/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code != 200:
            print(f"HTTP ошибка: {resp.status_code}")
            return None
        data = resp.json()
        if data.get("code") != 0:
            print(f"API ошибка: {data}")
            return None
        klines_raw = data.get("data", [])
        if not klines_raw:
            print("Нет данных в ответе")
            return None
        klines = []
        for k in reversed(klines_raw):
            klines.append({
                'timestamp': int(k[0]),
                'close': float(k[4]),
            })
        return klines
    except requests.exceptions.RequestException as e:
        print(f"Сетевая ошибка: {e}")
        return None
    except Exception as e:
        print(f"Неизвестная ошибка: {e}")
        return None

def calculate_sma(klines, period):
    if not klines or len(klines) < period:
        return None
    closes = [k['close'] for k in klines[-period:]]
    return sum(closes) / period

def main():
    print(f"Скрипт запущен. Слежу за {SYMBOL} ({TIMEFRAME})...")
    print("Нажмите Ctrl+C для выхода.")
    try:
        while True:
            clear_screen()
            print(f"{SYMBOL} | {TIMEFRAME} | {time.strftime('%Y-%m-%d %H:%M:%S')}")
            klines = fetch_klines(SYMBOL, TIMEFRAME, limit=100)
            if klines:
                last = klines[-1]
                print(f"Цена закрытия: {last['close']:.5f}")
                ma5 = calculate_sma(klines, 5)
                ma10 = calculate_sma(klines, 10)
                ma30 = calculate_sma(klines, 30)
                print(f"MA5  = {ma5:.5f}" if ma5 else "MA5  = недостаточно данных")
                print(f"MA10 = {ma10:.5f}" if ma10 else "MA10 = недостаточно данных")
                print(f"MA30 = {ma30:.5f}" if ma30 else "MA30 = недостаточно данных")
                # Дополнительно: последние 5 цен
                print("\nПоследние 5 цен закрытия:")
                for k in klines[-5:]:
                    dt = time.strftime('%H:%M:%S', time.localtime(k['timestamp'] / 1000))
                    print(f"{dt}  {k['close']:.5f}")
            else:
                print("Не удалось получить данные")
                print("Проверьте:")
                print(f"- Символ: {SYMBOL}")
                print(f"- Таймфрейм: {TIMEFRAME}")
                print(f"- URL: {BASE_URL}")
            time.sleep(60)
    except KeyboardInterrupt:
        print("\nЗавершено.")

if __name__ == "__main__":
    main()