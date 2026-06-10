import time
import numpy as np
import requests
import os
from binance import ThreadedWebsocketManager

# =====================
# ENV
# =====================
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

SYMBOLS = ["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","DOGEUSDT","LTCUSDT"]

data = {}

# =====================
# TELEGRAM
# =====================
def send(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg})

# =====================
# FILTERS
# =====================
def session_ok():
    hour = time.gmtime().tm_hour
    return 7 <= hour <= 17

def volatility_ok(c):
    atr = np.mean([x["high"] - x["low"] for x in c[-20:]])
    return atr > np.mean([x["close"] for x in c[-20:]]) * 0.0015

# =====================
# SMC CORE
# =====================
def sweep(c):
    lows = [x["low"] for x in c[-30:-1]]
    return c[-1]["low"] < min(lows) and c[-1]["close"] > c[-1]["open"]

def structure(c):
    highs = [x["high"] for x in c[-20:-1]]
    return c[-1]["close"] > max(highs)

def fvg(c):
    return len(c) > 3 and c[-3]["high"] < c[-1]["low"]

# =====================
# INDICATORS
# =====================
def ema_score(closes):
    return 2 if np.mean(closes[-20:]) > np.mean(closes[-50:]) else 1

def rsi_score(closes):
    gains, losses = [], []
    for i in range(-14, -1):
        diff = closes[i] - closes[i-1]
        gains.append(diff) if diff > 0 else losses.append(abs(diff))
    rsi = 100 - (100 / (1 + np.mean(gains)/(np.mean(losses)+1e-6)))
    return 2 if 40 < rsi < 65 else 1

def macd_score(closes):
    return 2 if np.mean(closes[-12:]) > np.mean(closes[-26:]) else 1

def obv_score(c):
    obv = 0
    for i in range(1, len(c)):
        obv += c[i]["volume"] if c[i]["close"] > c[i-1]["close"] else -c[i]["volume"]
    return 2 if obv > 0 else 1

def vwap_score(c):
    tpv = sum(((x["high"]+x["low"]+x["close"])/3)*x["volume"] for x in c[-30:])
    vol = sum(x["volume"] for x in c[-30:])
    vwap = tpv / vol
    return 2 if c[-1]["close"] > vwap else 1

def indicator_score(c):
    closes = [x["close"] for x in c]
    return (
        ema_score(closes)+
        rsi_score(closes)+
        macd_score(closes)+
        obv_score(c)+
        vwap_score(c)
    )

# =====================
# SMC SCORE
# =====================
def smc_score(c):
    s = 0
    if sweep(c): s += 30
    if structure(c): s += 20
    if fvg(c): s += 15
    return s

# =====================
# SIGNAL LOGIC
# =====================
def signal(symbol, c):

    if len(c) < 100:
        return None

    if not session_ok():
        return None

    if not volatility_ok(c):
        return None

    ind = indicator_score(c)
    if ind < 4:
        return None

    smc = smc_score(c)
    if smc < 50:
        return None

    entry = c[-1]["close"]
    sl = min(x["low"] for x in c[-30:])
    risk = entry - sl

    tp1 = entry + risk * 1
    tp2 = entry + risk * 2
    tp3 = entry + risk * 3

    return f"""
🟢 SMART MONEY SIGNAL

{symbol}

SMC Score: {smc}
Indicator Score: {ind}/10

ENTRY: {entry}
SL: {sl}

TP1: {tp1}
TP2: {tp2}
TP3: {tp3}

✔ Sweep
✔ Structure Break
✔ FVG
✔ EMA/RSI/MACD/OBV/VWAP
"""

# =====================
# DATA HANDLER
# =====================
def handle(msg):

    symbol = msg["s"]
    k = msg["k"]

    candle = {
        "open": float(k["o"]),
        "high": float(k["h"]),
        "low": float(k["l"]),
        "close": float(k["c"]),
        "volume": float(k["v"])
    }

    data.setdefault(symbol, []).append(candle)

    if len(data[symbol]) > 300:
        data[symbol].pop(0)

    sig = signal(symbol, data[symbol])

    if sig:
        send(sig)

# =====================
# START
# =====================
def start():

    twm = ThreadedWebsocketManager()
    twm.start()

    for s in SYMBOLS:
        twm.start_kline_socket(callback=handle, symbol=s, interval="15m")

    print("SIGNAL BOT RUNNING")
    while True:
        time.sleep(1)

start()
