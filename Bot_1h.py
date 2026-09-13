import math
import os
import time
import pandas as pd
import requests

# ===== TELEGRAM ТОХИРГОО =====
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8737624173:AAHNEb0nmuGLFZbypfIlpQWfyZ8KzeFbGJ4").strip()
CHAT_ID = os.getenv("CHAT_ID", "7837817666").strip()

BASE_URL = "https://api.binance.com"

def send_telegram_msg(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print("Telegram алдаа:", e)

def fmt(val):
    return f"{val:.4f}" if val < 10 else f"{val:.2f}"

class SMC1hSignalBot:
    def __init__(self, symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT", "AVAXUSDT", "NEARUSDT"], interval="1h"):
        self.symbols = symbols
        self.interval = interval
        self.last_signal_time = {}

    def get_klines(self, symbol, limit=100):
        url = f"{BASE_URL}/api/v3/klines?symbol={symbol}&interval={self.interval}&limit={limit}"
        try:
            resp = requests.get(url, timeout=5).json()
            if not isinstance(resp, list):
                return pd.DataFrame()
            candles = [{
                "Time": pd.to_datetime(c[0], unit='ms'),
                "Open": float(c[1]),
                "High": float(c[2]),
                "Low": float(c[3]),
                "Close": float(c[4])
            } for c in resp]
            return pd.DataFrame(candles)
        except Exception as e:
            print(f"{symbol} өгөгдөл татахад алдаа:", e)
            return pd.DataFrame()

    def run(self):
        print("🤖 SMC 1h Сигнал Бот ажиллаж байна...")
        send_telegram_msg("🚀 *1H SMC СИГНАЛ БОТ ЭХЭЛЛЭЭ*\nГрафик дээр SMC боломжуудыг хайж эхэллээ.")

        while True:
            for symbol in self.symbols:
                df = self.get_klines(symbol)
                if df.empty or len(df) < 55:
                    continue

                df['Swing_Low'] = (df['Low'] < df['Low'].shift(1)) & (df['Low'] < df['Low'].shift(-1))
                sub_df = df.iloc[-51:-1].copy()
                curr_candle = df.iloc[-1]

                sma_50 = sub_df['Close'].mean()
                if curr_candle['Close'] < sma_50:
                    continue

                highs = sub_df['High'].values
                lows = sub_df['Low'].values
                if len(highs) == 0 or len(lows) == 0:
                    continue

                dealing_high = max(highs)
                dealing_low = min(lows)
                diff = dealing_high - dealing_low

                if diff == 0:
                    continue

                recent_sl_val = sub_df[sub_df['Swing_Low']]['Low'].tail(1)
                if recent_sl_val.empty:
                    continue
                recent_sl = float(recent_sl_val.values[0])

                recent_slice = sub_df.tail(5)
                has_sweep = any((recent_slice['Low'] < recent_sl) & (recent_slice['Close'] > recent_sl))
                if not has_sweep:
                    continue

                ote_high = dealing_high - (diff * 0.618)
                ote_low = dealing_high - (diff * 0.79)

                if curr_candle['Low'] <= ote_high and curr_candle['High'] >= ote_low:
                    now = curr_candle['Time']
                    if symbol in self.last_signal_time:
                        time_diff = (now - self.last_signal_time[symbol]).total_seconds() / 3600
                        if time_diff < 1:
                            continue

                    self.last_signal_time[symbol] = now

                    entry_price = (ote_high + ote_low) / 2
                    stop_loss = recent_sl - (diff * 0.005)
                    risk = entry_price - stop_loss
                    if risk <= 0:
                        continue
                    take_profit = entry_price + (risk * 3)

                    msg = (
                        f"🎯 *SMC 1H СИГНАЛ ОЛДЛОО ({symbol})*\n\n"
                        f"📥 *Entry (Орох бүс):* `{fmt(entry_price)}`\n"
                        f"🛑 *Stop Loss:* `{fmt(stop_loss)}`\n"
                        f"🎯 *Take Profit (1:3):* `{fmt(take_profit)}`\n\n"
                        f"💡 *Тайлбар:* Swing low sweep болон OTE бүсэд үнэ хүрлээ."
                    )
                    send_telegram_msg(msg)

            time.sleep(3600)

if __name__ == "__main__":
    bot = SMC1hSignalBot(interval="1h")
    bot.run()
