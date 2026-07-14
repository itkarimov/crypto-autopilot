# -*- coding: utf-8 -*-
"""Уровни поддержки/сопротивления: свинг-точки на 1h/4h/1D + классические пивоты.
Аналог того, что показывает TradingView (те же формулы)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bybit_client import pub


def klines(symbol, interval, limit):
    r = pub("/v5/market/kline", {"category": "spot", "symbol": symbol, "interval": interval, "limit": str(limit)})
    # список от новых к старым: [ts, open, high, low, close, vol, turnover]
    return [[float(x) for x in c[1:5]] for c in r["result"]["list"]]


def swings(candles, wing=3):
    """Локальные максимумы/минимумы: high выше wing соседей с обеих сторон."""
    highs, lows = [], []
    for i in range(wing, len(candles) - wing):
        h = candles[i][1]
        l = candles[i][2]
        if all(h >= candles[j][1] for j in range(i - wing, i + wing + 1)):
            highs.append(h)
        if all(l <= candles[j][2] for j in range(i - wing, i + wing + 1)):
            lows.append(l)
    return highs, lows


def pivots(symbol):
    """Классические дневные пивоты от вчерашней свечи (P, R1, R2, S1, S2)."""
    d = klines(symbol, "D", 3)
    o, h, l, c = d[1]  # вчерашняя закрытая свеча
    p = (h + l + c) / 3
    return {"P": p, "R1": 2 * p - l, "R2": p + (h - l), "S1": 2 * p - h, "S2": p - (h - l)}


def analyze(symbol):
    last = float(pub("/v5/market/tickers", {"category": "spot", "symbol": symbol})["result"]["list"][0]["lastPrice"])
    print(f"\n=== {symbol}: текущая {last} ===")
    pv = pivots(symbol)
    print("Пивоты (день):", ", ".join(f"{k}={v:.4g}" for k, v in pv.items()))
    for tf, lim, wing in [("60", 168, 3), ("240", 180, 3), ("D", 90, 2)]:
        hs, ls = swings(klines(symbol, tf, lim), wing)
        res = sorted([h for h in hs if h > last])[:3]
        sup = sorted([l for l in ls if l < last], reverse=True)[:3]
        name = {"60": "1h", "240": "4h", "D": "1D"}[tf]
        r_str = ", ".join(f"{r:.4g} (+{(r / last - 1) * 100:.1f}%)" for r in res) or "—"
        s_str = ", ".join(f"{s:.4g} ({(s / last - 1) * 100:.1f}%)" for s in sup) or "—"
        print(f"  {name}: сопротивления {r_str}")
        print(f"      поддержки    {s_str}")


for sym in ["SOLUSDT", "LINKUSDT", "UNIUSDT"]:
    analyze(sym)
