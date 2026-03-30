import sys
sys.path.append('D:\\Projects\\screener RSI')
from app.tradebot.bingx_exchange_info import BingxExchangeInfo
import time

# Запускаем фоновый поток для загрузки символов
info = BingxExchangeInfo()
info.start()
# Ждём 5 секунд, чтобы загрузились данные
time.sleep(5)

print(f"Всего символов в original_symbols: {len(BingxExchangeInfo.original_symbols)}")
print("Примеры символов (чистые):", list(BingxExchangeInfo.original_symbols.keys())[:10])
print("Примеры оригинальных символов (с дефисом):", list(BingxExchangeInfo.original_symbols.values())[:10])