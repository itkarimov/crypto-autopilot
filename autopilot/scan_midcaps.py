# -*- coding: utf-8 -*-
"""Скан ликвидных средних монет: цена, динамика 7/30/90д, объём, волатильность."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bybit_client import pub

SYMBOLS = ["SOLUSDT", "LINKUSDT", "XRPUSDT", "AVAXUSDT", "DOTUSDT", "ADAUSDT",
           "LTCUSDT", "UNIUSDT", "ATOMUSDT", "NEARUSDT", "TONUSDT", "ETHUSDT"]

print(f"{'Пара':<10} {'Цена':>10} {'24ч%':>7} {'7д%':>7} {'30д%':>7} {'90д%':>8} {'Объём24ч $M':>12} {'Вола30д%':>9}")
for sym in SYMBOLS:
    try:
        t = pub("/v5/market/tickers", {"category": "spot", "symbol": sym})["result"]["list"][0]
        k = pub("/v5/market/kline", {"category": "spot", "symbol": sym, "interval": "D", "limit": "91"})["result"]["list"]
        last = float(t["lastPrice"])
        closes = [float(c[4]) for c in k]  # k[0] — сегодня, дальше в прошлое
        c7 = (last / closes[7] - 1) * 100 if len(closes) > 7 else float("nan")
        c30 = (last / closes[30] - 1) * 100 if len(closes) > 30 else float("nan")
        c90 = (last / closes[90] - 1) * 100 if len(closes) > 90 else float("nan")
        vol_usd = float(t["turnover24h"]) / 1e6
        # волатильность: средний дневной размах (high-low)/close за 30 дней
        rng = [(float(c[2]) - float(c[3])) / float(c[4]) * 100 for c in k[:30]]
        vola = sum(rng) / len(rng)
        print(f"{sym:<10} {last:>10.4g} {float(t['price24hPcnt'])*100:>+7.1f} {c7:>+7.1f} {c30:>+7.1f} {c90:>+8.1f} {vol_usd:>12.1f} {vola:>9.2f}")
    except Exception as e:
        print(f"{sym:<10} ошибка: {e}")
