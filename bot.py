import os
import asyncio
import json
import requests
import pandas as pd
import numpy as np
from datetime import datetime
from collections import deque
from dotenv import load_dotenv
import websockets

load_dotenv()

# --- ENV VARIABLES ---
DERIV_API_TOKEN = os.getenv("DERIV_API_TOKEN")
SYMBOL = os.getenv("SYMBOL", "R_25")
FAST_SMA = int(os.getenv("FAST_SMA", 9))
SLOW_SMA = int(os.getenv("SLOW_SMA", 21))
RSI_PERIOD = int(os.getenv("RSI_PERIOD", 14))
ATR_PERIOD = int(os.getenv("ATR_PERIOD", 14))
ATR_MULT_SL = float(os.getenv("ATR_MULT_SL", 2))
ATR_MULT_TP = float(os.getenv("ATR_MULT_TP", 4))
STAKE = float(os.getenv("STAKE", 1))

# --- Candle Storage ---
CANDLES_HISTORY = 100
candles = deque(maxlen=CANDLES_HISTORY)

# --- Indicators ---
def sma(series, period):
    return pd.Series(series).rolling(period).mean().iloc[-1]

def rsi(series, period):
    series = pd.Series(series)
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean().iloc[-1]
    avg_loss = loss.rolling(period).mean().iloc[-1]
    rs = avg_gain / avg_loss if avg_loss != 0 else 0
    return 100 - (100 / (1 + rs))

def atr(highs, lows, closes, period):
    highs = pd.Series(highs)
    lows = pd.Series(lows)
    closes = pd.Series(closes)
    tr1 = highs - lows
    tr2 = (highs - closes.shift()).abs()
    tr3 = (lows - closes.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(period).mean().iloc[-1]

# --- Place Deriv Trade ---
async def place_trade(direction, entry_price, stop_loss, take_profit):
    trade_data = {
        "buy": 1,
        "parameters": {
            "amount": STAKE,
            "basis": "stake",
            "contract_type": "CALL" if direction=="BUY" else "PUT",
            "currency": "USD",
            "duration": 1,
            "duration_unit": "m",
            "symbol": SYMBOL
        }
    }
    # Deriv API HTTP call
    async with websockets.connect(f"wss://ws.derivws.com/websockets/v3?app_id=1089") as ws:
        await ws.send(json.dumps({"authorize": DERIV_API_TOKEN}))
        await ws.send(json.dumps(trade_data))
        resp = await ws.recv()
        print("Trade response:", resp)

# --- Main Loop ---
async def main():
    async with websockets.connect(f"wss://ws.derivws.com/websockets/v3?app_id=1089") as ws:
        await ws.send(json.dumps({"authorize": DERIV_API_TOKEN}))
        # Subscribe to 1-minute candles
        await ws.send(json.dumps({
            "ticks_history": SYMBOL,
            "granularity": 60,
            "start": 1,
            "end": "latest",
            "style": "candles"
        }))
        print("Subscribed to 1-minute candles")
        
        highs, lows, closes = deque(maxlen=CANDLES_HISTORY), deque(maxlen=CANDLES_HISTORY), deque(maxlen=CANDLES_HISTORY)
        last_signal = None

        async for msg in ws:
            data = json.loads(msg)
            if "candles" in data:
                for c in data["candles"]:
                    closes.append(float(c["close"]))
                    highs.append(float(c["high"]))
                    lows.append(float(c["low"]))
                if len(closes) >= max(FAST_SMA, SLOW_SMA, RSI_PERIOD, ATR_PERIOD):
                    fast_sma = sma(list(closes), FAST_SMA)
                    slow_sma = sma(list(closes), SLOW_SMA)
                    rsi_val = rsi(list(closes), RSI_PERIOD)
                    atr_val = atr(list(highs), list(lows), list(closes), ATR_PERIOD)
                    price = closes[-1]

                    direction = None
                    if price > slow_sma and fast_sma > slow_sma and rsi_val > 50:
                        direction = "BUY"
                    elif price < slow_sma and fast_sma < slow_sma and rsi_val < 50:
                        direction = "SELL"

                    if direction and last_signal != direction:
                        sl = price - ATR_MULT_SL*atr_val if direction=="BUY" else price + ATR_MULT_SL*atr_val
                        tp = price + ATR_MULT_TP*atr_val if direction=="BUY" else price - ATR_MULT_TP*atr_val
                        print(f"{datetime.utcnow()} | {direction} | Entry: {price} | SL: {sl} | TP: {tp}")
                        await place_trade(direction, price, sl, tp)
                        last_signal = direction

if __name__ == "__main__":
    asyncio.run(main())
