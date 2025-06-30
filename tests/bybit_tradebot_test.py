from app.tradebot.bybit import BybitTradebot
from app.schemas import SignalDTO, SignalSide
from app.core import config


def main():
    signal = SignalDTO(
        side=SignalSide.BUY,
        symbol="BTCUSDT",
        prev_rsi=0,
        curr_rsi=1,
        klines=[{"c": 107582}],  # type: ignore
    )
    bot = BybitTradebot(config.BYBIT_API_KEY, config.BYBIT_API_SECRET)

    import time

    time.sleep(5)

    bot.process_signal(signal=signal)


if __name__ == "__main__":
    main()
