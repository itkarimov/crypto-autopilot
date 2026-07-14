# -*- coding: utf-8 -*-
"""Снапшот: баланс UNIFIED + цены/динамика мейджоров на споте."""
import json
import os
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bybit_client import get


def pub(path, params):
    q = urllib.parse.urlencode(params)
    with urllib.request.urlopen("https://api.bybit.com" + path + "?" + q, timeout=15) as r:
        return json.loads(r.read().decode())


bal = get("/v5/account/wallet-balance", {"accountType": "UNIFIED"})
acc = bal["result"]["list"][0]
print("Equity:", acc["totalEquity"], "USD")
for c in acc.get("coin", []):
    if float(c.get("equity") or 0) > 0.001:
        print(f"  {c['coin']}: {c['equity']} (~{float(c.get('usdValue') or 0):.2f} USD)")

print()
for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT", "MNTUSDT"]:
    t = pub("/v5/market/tickers", {"category": "spot", "symbol": sym})["result"]["list"][0]
    k = pub("/v5/market/kline", {"category": "spot", "symbol": sym, "interval": "D", "limit": "31"})["result"]["list"]
    last = float(t["lastPrice"])
    c7 = (last / float(k[7][4]) - 1) * 100 if len(k) > 7 else 0
    c30 = (last / float(k[30][4]) - 1) * 100 if len(k) > 30 else 0
    print(f"{sym}: {last}  24h {float(t['price24hPcnt']) * 100:+.1f}%  7d {c7:+.1f}%  30d {c30:+.1f}%")
