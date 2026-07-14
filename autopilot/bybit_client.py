# -*- coding: utf-8 -*-
"""Клиент Bybit V5: подписанные GET/POST + хелперы спот-торговли."""
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.parse
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_env():
    env = {}
    path = os.path.join(BASE_DIR, ".env")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    return env


_ENV = _load_env()
# .get с дефолтом: на GitHub-раннере ключей Bybit НЕТ (все вызовы Bybit идут по SSH на сервер),
# импорт не должен падать. Подписанные вызовы без ключей просто вернут ошибку авторизации.
API_KEY = _ENV.get("BYBIT_API_KEY", "")
API_SECRET = _ENV.get("BYBIT_API_SECRET", "")
HOST = "https://api-testnet.bybit.com" if _ENV.get("BYBIT_ENV") == "testnet" else "https://api.bybit.com"
RECV = "15000"
_TIME_OFFSET = None


def _server_offset():
    global _TIME_OFFSET
    if _TIME_OFFSET is None:
        with urllib.request.urlopen("https://api.bybit.com/v5/market/time", timeout=10) as r:
            server_ms = int(json.loads(r.read().decode())["result"]["timeNano"]) // 1_000_000
        _TIME_OFFSET = server_ms - int(time.time() * 1000)
    return _TIME_OFFSET


def _headers(payload):
    ts = str(int(time.time() * 1000) + _server_offset())
    sign = hmac.new(API_SECRET.encode(), (ts + API_KEY + RECV + payload).encode(), hashlib.sha256).hexdigest()
    return {
        "X-BAPI-API-KEY": API_KEY,
        "X-BAPI-TIMESTAMP": ts,
        "X-BAPI-RECV-WINDOW": RECV,
        "X-BAPI-SIGN": sign,
        "Content-Type": "application/json",
    }


def get(path, params=None):
    query = urllib.parse.urlencode(params or {})
    req = urllib.request.Request(HOST + path + ("?" + query if query else ""), headers=_headers(query))
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def post(path, body):
    data = json.dumps(body)
    req = urllib.request.Request(HOST + path, data=data.encode(), headers=_headers(data), method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def pub(path, params=None):
    query = urllib.parse.urlencode(params or {})
    req = urllib.request.Request("https://api.bybit.com" + path + ("?" + query if query else ""))
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def instrument(symbol):
    r = pub("/v5/market/instruments-info", {"category": "spot", "symbol": symbol})
    return r["result"]["list"][0]


def spot_order(symbol, side, order_type, qty, price=None, market_unit=None):
    """qty — строка. Для Market Buy qty в USDT (marketUnit=quoteCoin по умолч.), для Sell — в монете."""
    body = {"category": "spot", "symbol": symbol, "side": side, "orderType": order_type, "qty": str(qty)}
    if price:
        body["price"] = str(price)
    if market_unit:
        body["marketUnit"] = market_unit
    return post("/v5/order/create", body)


def balances():
    acc = get("/v5/account/wallet-balance", {"accountType": "UNIFIED"})["result"]["list"][0]
    out = {"totalEquity": float(acc["totalEquity"])}
    for c in acc.get("coin", []):
        eq = float(c.get("equity") or 0)
        if eq > 1e-9:
            out[c["coin"]] = {"qty": eq, "usd": float(c.get("usdValue") or 0)}
    return out
