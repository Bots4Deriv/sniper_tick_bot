import asyncio
import json
import websockets
import pandas as pd
import requests
import os

# ENV VARIABLES
DERIV_TOKEN = os.getenv("DERIV_API_TOKEN")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

SYMBOL = "R_25"
FAST_SMA = 9
SLOW_SMA = 21
RSI_PERIOD = 14

closes = []


def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": message}
    requests.post(url, data=data)


def calculate_rsi(series, period):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


async def main():

    url = "wss://ws.derivws.com/websockets/v3?app_id=1089"

    async with websockets.connect(url) as ws:

        await ws.send(json.dumps({"authorize": DERIV_TOKEN}))
        print(await ws.recv())

        await ws.send(json.dumps({
            "ticks_history": SYMBOL,
            "granularity": 60,
            "subscribe": 1,
            "style": "candles"
        }))

        print("Bot running...")

        last_signal = None

        while True:

            data = json.loads(await ws.recv())

            if "candles" in data:

                candle = data["candles"][-1]
                close = float(candle["close"])

                closes.append(close)

                if len(closes) > 100:
                    closes.pop(0)

                if len(closes) > SLOW_SMA:

                    df = pd.DataFrame(closes, columns=["close"])

                    fast = df["close"].rolling(FAST_SMA).mean().iloc[-1]
                    slow = df["close"].rolling(SLOW_SMA).mean().iloc[-1]
                    rsi = calculate_rsi(df["close"], RSI_PERIOD).iloc[-1]

                    signal = None

                    if close > slow and fast > slow and rsi > 50:
                        signal = "BUY"

                    if close < slow and fast < slow and rsi < 50:
                        signal = "SELL"

                    if signal and signal != last_signal:

                        msg = f"""
📊 R25 SIGNAL

Signal: {signal}
Price: {close}

SMA9: {round(fast,2)}
SMA21: {round(slow,2)}
RSI: {round(rsi,2)}
"""

                        send_telegram(msg)

                        print(msg)

                        last_signal = signal


asyncio.run(main())
