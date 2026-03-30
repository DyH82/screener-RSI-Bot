import json
import time
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Any

from app.core import config, logger


class TradeRecord:
    def __init__(self, symbol: str, side: str, entry_price: float, quantity: float,
                 tp_price: float, sl_price: float, balance: float, leverage: int = 0):
        self.symbol = symbol
        self.side = side
        self.type = "LONG" if side == "BUY" else "SHORT"
        self.entry_price = entry_price
        self.quantity = quantity
        self.tp_price = tp_price
        self.sl_price = sl_price
        self.leverage = leverage
        self.open_time = datetime.now()
        self.close_time: Optional[datetime] = None
        self.exit_price: Optional[float] = None
        self.pnl_usdt: Optional[float] = None
        self.pnl_percent: Optional[float] = None
        self.start_balance = balance
        self.end_balance: Optional[float] = None

    def close(self, exit_price: float, balance: float):
        self.close_time = datetime.now()
        self.exit_price = exit_price
        if self.side == "BUY":
            self.pnl_usdt = (exit_price - self.entry_price) * self.quantity
        else:
            self.pnl_usdt = (self.entry_price - exit_price) * self.quantity
        if (self.entry_price * self.quantity) != 0:
            self.pnl_percent = (self.pnl_usdt / (self.entry_price * self.quantity)) * 100
        else:
            self.pnl_percent = 0.0
        self.end_balance = balance

    def to_dict(self) -> dict:
        return {
            "open_time": self.open_time.strftime("%Y-%m-%dT%H:%M:%S"),
            "close_time": self.close_time.strftime("%Y-%m-%dT%H:%M:%S") if self.close_time else "",
            "symbol": self.symbol,
            "type": self.type,
            "side": self.side,
            "entry_price": round(self.entry_price, 5),
            "exit_price": round(self.exit_price, 5) if self.exit_price else 0,
            "quantity": round(self.quantity, 5),
            "leverage": self.leverage,
            "tp_price": round(self.tp_price, 5) if self.tp_price else 0,
            "sl_price": round(self.sl_price, 5) if self.sl_price else 0,
            "pnl_usdt": round(self.pnl_usdt, 5) if self.pnl_usdt else 0,
            "pnl_percent": round(self.pnl_percent, 2) if self.pnl_percent else 0,
            "start_balance": round(self.start_balance, 5),
            "end_balance": round(self.end_balance, 5) if self.end_balance else self.start_balance,
        }


class StatsCollector:
    def __init__(self):
        self.trades: List[TradeRecord] = []
        self.open_trades: Dict[tuple, TradeRecord] = {}
        self.total_pnl_usdt = 0.0
        self.win_count = 0
        self.loss_count = 0
        self._stats_file = Path("stats.json")
        self._load_from_file()

    def _load_from_file(self):
        if not self._stats_file.exists():
            return
        try:
            with open(self._stats_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for trade_dict in data.get("trades", []):
                trade = TradeRecord(
                    symbol=trade_dict["symbol"],
                    side=trade_dict["side"],
                    entry_price=trade_dict["entry_price"],
                    quantity=trade_dict["quantity"],
                    tp_price=trade_dict["tp_price"],
                    sl_price=trade_dict["sl_price"],
                    balance=trade_dict["start_balance"],
                    leverage=trade_dict["leverage"],
                )
                trade.open_time = datetime.fromisoformat(trade_dict["open_time"])
                trade.close_time = datetime.fromisoformat(trade_dict["close_time"])
                trade.exit_price = trade_dict["exit_price"]
                trade.pnl_usdt = trade_dict["pnl_usdt"]
                trade.pnl_percent = trade_dict["pnl_percent"]
                trade.end_balance = trade_dict["end_balance"]
                self.trades.append(trade)
                if trade.pnl_usdt > 0:
                    self.win_count += 1
                else:
                    self.loss_count += 1
                self.total_pnl_usdt += trade.pnl_usdt
            logger.info(f"Загружено {len(self.trades)} завершённых сделок из {self._stats_file}")
        except Exception as e:
            logger.error(f"Ошибка загрузки статистики: {e}")

    def _save_to_file(self):
        try:
            data = {"trades": [t.to_dict() for t in self.trades]}
            with open(self._stats_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Ошибка сохранения статистики: {e}")

    def sync_open_trades_from_exchange(self, tradebot):
        try:
            positions = tradebot._get_positions(use_cache=False)
            for pos in positions:
                symbol = pos["symbol"]
                side = "BUY" if pos["side"] == "long" else "SELL"
                key = (symbol, side)
                if key not in self.open_trades:
                    trade = TradeRecord(
                        symbol=symbol,
                        side=side,
                        entry_price=pos.get("entry_price", 0.0),
                        quantity=pos.get("quantity", 0.0),
                        tp_price=pos.get("tp_price", 0.0),
                        sl_price=pos.get("sl_price", 0.0),
                        balance=0.0,
                        leverage=0
                    )
                    trade.open_time = datetime.now()
                    self.open_trades[key] = trade
                    logger.info(f"Восстановлена открытая позиция из биржи: {symbol} {side}")
        except Exception as e:
            logger.error(f"Ошибка синхронизации открытых позиций: {e}")

    def record_open(self, symbol: str, side: str, entry_price: float, quantity: float,
                    tp_price: float, sl_price: float, balance: float, leverage: int = 0):
        key = (symbol, side)
        if key in self.open_trades:
            logger.warning(f"Trade {key} already open, closing old one.")
            self.record_close(symbol, side, entry_price, balance)
        trade = TradeRecord(symbol, side, entry_price, quantity, tp_price, sl_price, balance, leverage)
        self.open_trades[key] = trade
        logger.debug(f"Статистика: открыта сделка {key} (leverage={leverage})")

    def record_close(self, symbol: str, side: str, exit_price: float, balance: float):
        key = (symbol, side)
        trade = self.open_trades.pop(key, None)
        if not trade:
            alt_side = "BUY" if side == "SELL" else "SELL"
            trade = self.open_trades.pop((symbol, alt_side), None)
            if not trade:
                logger.warning(f"Статистика: попытка закрыть несуществующую сделку {key}")
                return
        trade.close(exit_price, balance)
        self.trades.append(trade)
        self._save_to_file()

        if trade.pnl_usdt > 0:
            self.win_count += 1
        else:
            self.loss_count += 1
        self.total_pnl_usdt += trade.pnl_usdt

        logger.info(
            f"📊 Сделка {trade.symbol} {trade.type} закрыта: "
            f"PnL={trade.pnl_usdt:.2f} USDT ({trade.pnl_percent:.1f}%)"
        )

    def print_summary(self):
        total_trades = len(self.trades)
        win_rate = self.win_count / total_trades * 100 if total_trades else 0
        avg_win = sum(t.pnl_usdt for t in self.trades if t.pnl_usdt > 0) / self.win_count if self.win_count else 0
        avg_loss = sum(t.pnl_usdt for t in self.trades if t.pnl_usdt < 0) / self.loss_count if self.loss_count else 0
        profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 else float('inf')

        print("\n" + "="*50)
        print("📈 СТАТИСТИКА ТОРГОВЛИ")
        print("="*50)
        print(f"Всего сделок:           {total_trades}")
        print(f"Прибыльных:             {self.win_count} ({win_rate:.1f}%)")
        print(f"Убыточных:              {self.loss_count}")
        print(f"Суммарный PnL:          {self.total_pnl_usdt:.2f} USDT")
        print(f"Средняя прибыль:        {avg_win:.2f} USDT")
        print(f"Средний убыток:         {avg_loss:.2f} USDT")
        print(f"Фактор прибыли:         {profit_factor:.2f}")
        print("="*50)

        if total_trades > 0:
            print("\n📋 Последние 5 сделок:")
            for t in self.trades[-5:]:
                print(f"{t.close_time.strftime('%m-%d %H:%M')} {t.symbol} {t.type:4} "
                      f"цена={t.exit_price:.6f} PnL={t.pnl_usdt:+.2f} USDT ({t.pnl_percent:+.1f}%)")
        else:
            print("\n📋 Нет завершённых сделок.")

        if self.open_trades:
            print(f"\n📂 Открытые позиции ({len(self.open_trades)}):")
            for (symbol, side), trade in self.open_trades.items():
                print(f"{symbol} {trade.type} цена={trade.entry_price:.5f} кол-во={trade.quantity:.2f} TP={trade.tp_price:.5f} SL={trade.sl_price:.5f}")
        else:
            print("\n📂 Открытых позиций нет.")

    def print_time_breakdown(self):
        if not self.trades:
            print("📊 Нет завершённых сделок.")
            return

        periods = {
            "🌙 Ночь (00:00-06:00)": (0, 6),
            "🌅 Утро (06:00-12:00)": (6, 12),
            "☀️ День (12:00-18:00)": (12, 18),
            "🌆 Вечер (18:00-24:00)": (18, 24),
        }

        breakdown = {}
        for period_name, (start_hour, end_hour) in periods.items():
            period_pnl = 0.0
            period_count = 0
            period_win = 0
            period_loss = 0
            sum_win = 0.0
            sum_loss = 0.0
            for trade in self.trades:
                if trade.close_time is None:
                    continue
                hour = trade.close_time.hour
                if start_hour <= hour < end_hour:
                    period_count += 1
                    period_pnl += trade.pnl_usdt
                    if trade.pnl_usdt > 0:
                        period_win += 1
                        sum_win += trade.pnl_usdt
                    else:
                        period_loss += 1
                        sum_loss += trade.pnl_usdt
            breakdown[period_name] = (period_count, period_win, period_loss, period_pnl, sum_win, abs(sum_loss))

        print("\n" + "="*70)
        print("📊 ПРИБЫЛЬ/УБЫТОК ПО ВРЕМЕНИ СУТОК")
        print("="*70)
        for period_name, (count, win, loss, pnl, sum_win, sum_loss) in breakdown.items():
            avg = pnl / count if count else 0
            win_rate = (win / count * 100) if count else 0
            print(f"{period_name:<25} | Всего: {count:3} | Прибыльных: {win:3} ({win_rate:5.1f}%) | Сумма прибыли: {sum_win:8.2f} | Убыточных: {loss:3} | Сумма убытка: {sum_loss:8.2f} | PnL: {pnl:+.2f} | Средняя: {avg:+.2f}")
        print("="*70)

    def reset(self):
        self.trades.clear()
        self.open_trades.clear()
        self.total_pnl_usdt = 0.0
        self.win_count = 0
        self.loss_count = 0
        if self._stats_file.exists():
            self._stats_file.unlink()
            logger.info(f"Удалён файл {self._stats_file}")
        if config.STATS_CSV_PATH and Path(config.STATS_CSV_PATH).exists():
            Path(config.STATS_CSV_PATH).unlink()
            logger.info(f"Удалён файл {config.STATS_CSV_PATH}")
        logger.success("Статистика сброшена.")