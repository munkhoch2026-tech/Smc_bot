import math
import os
import time
import hmac
import hashlib
import urllib.parse
import pandas as pd
import requests

# ===== TELEGRAM ТОХИРГОО =====
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8737624173:AAHNEb0nmuGLFZbypfIlpQWfyZ8KzeFbGJ4").strip()
CHAT_ID = os.getenv("CHAT_ID", "7837817666").strip()

# ===== BINANCE SPOT TESTNET API ТОХИРГОО =====
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "En7fAi4G1xQFG17arU3weWgk8ejn2E8LxU4mMnF9oypYpFyno5nRLUJDTJ38GbYh").strip()
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY", "sVFIXH6Ma0FKTx0MC5kurhltf3Lok0PZyD2OgY0w6Xa4VDGJhfgdZzkf0KZzgo7o").strip()

BASE_URL = "https://testnet.binance.vision"
TRADE_USDT_AMOUNT = 20

def send_telegram_msg(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print("Telegram алдаа:", e)

def fmt(val):
    return f"{val:.4f}" if val < 10 else f"{val:.2f}"

def sign_query(params, secret_key):
    query_string = urllib.parse.urlencode(params)
    signature = hmac.new(
        secret_key.encode('utf-8'),
        query_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    return f"{query_string}&signature={signature}"

class RobustAutoSMCBot:
    def __init__(self, symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT", "AVAXUSDT", "NEARUSDT"], interval="1h"):
        self.symbols = symbols
        self.interval = interval
        self.last_signal_time = {}

    def round_step(self, value, step_size):
        precision = int(round(-math.log10(float(step_size))))
        return round(value, precision)

    def get_symbol_info(self, symbol):
        try:
            url = f"{BASE_URL}/api/v3/exchangeInfo?symbol={symbol}"
            resp = requests.get(url, timeout=5).json()
            symbol_info = resp['symbols'][0]
            lot_size = next(f for f in symbol_info['filters'] if f['filterType'] == 'LOT_SIZE')
            price_filter = next(f for f in symbol_info['filters'] if f['filterType'] == 'PRICE_FILTER')
            return float(lot_size['stepSize']), float(price_filter['tickSize'])
        except Exception as e:
            print(f"{symbol} info татахад алдаа:", e)
            return None, None

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

    def send_signed_order(self, params):
        url = f"{BASE_URL}/api/v3/order"
        params['timestamp'] = int(time.time() * 1000)
        query_str = sign_query(params, BINANCE_SECRET_KEY)
        headers = {"X-MBX-APIKEY": BINANCE_API_KEY}
        resp = requests.post(f"{url}?{query_str}", headers=headers, timeout=5)
        return resp.json()

    def execute_safe_trade(self, symbol, entry_price, stop_loss, take_profit):
        step_size, tick_size = self.get_symbol_info(symbol)
        if not step_size or not tick_size:
            send_telegram_msg(f"⚠️ *{symbol}* хосын оронгийн нарийвчлалыг татаж чадсангүй.")
            return

        try:
            raw_qty = TRADE_USDT_AMOUNT / entry_price
            quantity = self.round_step(raw_qty, step_size)

            # 1. Market Buy
            buy_params = {
                "symbol": symbol,
                "side": "BUY",
                "type": "MARKET",
                "quantity": quantity
            }
            buy_res = self.send_signed_order(buy_params)

            if "code" in buy_res and buy_res["code"] != 200:
                raise Exception(f"APIError(code={buy_res['code']}): {buy_res.get('msg')}")

            executed_qty = float(buy_res.get('executedQty', quantity))

            stop_loss_price = self.round_step(stop_loss, tick_size)
            take_profit_price = self.round_step(take_profit, tick_size)

            # 2. Limit Sell (Take Profit)
            tp_params = {
                "symbol": symbol,
                "side": "SELL",
                "type": "LIMIT",
                "timeInForce": "GTC",
                "quantity": executed_qty,
                "price": str(take_profit_price)
            }
            self.send_signed_order(tp_params)

            # 3. Stop Loss Limit
            sl_params = {
                "symbol": symbol,
                "side": "SELL",
                "type": "STOP_LOSS_LIMIT",
                "timeInForce": "GTC",
                "quantity": executed_qty,
                "price": str(self.round_step(stop_loss_price * 0.998, tick_size)),
                "stopPrice": str(stop_loss_price)
            }
            self.send_signed_order(sl_params)

            msg = (
                f"⚡ *1H ТЕСТНЕТ АРИЛЖАА НЭЭГДЛЭЭ ({symbol})*\n\n"
                f"💵 *Ашигласан дүн:* {TRADE_USDT_AMOUNT}$\n"
                f"📦 *Авсан хэмжээ:* {executed_qty}\n"
                f"🎯 *Entry:* `{fmt(entry_price)}`\n"
                f"🛑 *Stop Loss:* `{fmt(stop_loss_price)}`\n"
                f"🎯 *Take Profit:* `{fmt(take_profit_price)}`\n\n"
                f"🛡️ *Байршуулсан:* SL болон TP захиалгууд бэлэн байна."
            )
            send_telegram_msg(msg)

        except Exception as e:
            err_msg = f"❌ *{symbol} 1h Арилжаа нээхэд алдаа гарлаа:* {str(e)}"
            send_telegram_msg(err_msg)
            print(err_msg)

    def run(self):
        print("🤖 Binance Testnet SMC 1h Бот ажиллаж байна...")
        send_telegram_msg("🚀 *1H ТЕСТНЕТ БОТ ЭХЭЛЛЭЭ*\nБинанс туршилтын сервер дээр 1 цагийн арилжааг шалгаж эхэллээ.")

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

                    self.execute_safe_trade(symbol, entry_price, stop_loss, take_profit)

            time.sleep(3600)

if __name__ == "__main__":
    bot = RobustAutoSMCBot(interval="1h")
    bot.run()
