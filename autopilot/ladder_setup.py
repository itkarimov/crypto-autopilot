# -*- coding: utf-8 -*-
"""Мини-грид на откуп: снять старые откупные лимитки и выставить лестницу
из 2-3 ордеров на ближайших поддержках (уровни от ТЕКУЩЕЙ цены).
Запуск: python3 ladder_setup.py [COIN ...] (по умолчанию все в статусе rebuy)."""
import json
import math
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
from bybit_client import balances, get, instrument, post, pub, spot_order
from levels import klines, pivots, swings

STATE = os.path.join(BASE, "positions.json")


def fmt_qty(sym, q):
    bp = instrument(sym)["lotSizeFilter"]["basePrecision"]
    d = len(bp.split(".")[1]) if "." in bp else 0
    return f"{math.floor(q / float(bp)) * float(bp):.{d}f}"


def fmt_price(sym, pr):
    tick = instrument(sym)["priceFilter"]["tickSize"]
    d = len(tick.split(".")[1]) if "." in tick else 0
    return f"{math.floor(pr / float(tick)) * float(tick):.{d}f}"


def support_levels(sym, last, n=3):
    """До n поддержек ниже цены: свинги 1h/4h + дневные пивоты, разнесены ≥0.8%."""
    cands = []
    for tf, lim, wing in [("60", 168, 3), ("240", 180, 3)]:
        _, lows = swings(klines(sym, tf, lim), wing)
        cands += lows
    pv = pivots(sym)
    cands += [pv["S1"], pv["S2"], pv["P"]]
    cands = sorted({c for c in cands if last * 0.90 <= c <= last * 0.995}, reverse=True)
    out = []
    for c in cands:
        if all(abs(c / o - 1) >= 0.008 for o in out):
            out.append(c)
        if len(out) == n:
            break
    # fallback-и, если уровней мало
    fb = [last * 0.99, last * 0.972, last * 0.95]
    for f in fb:
        if len(out) >= n:
            break
        if all(abs(f / o - 1) >= 0.008 for o in out):
            out.append(f)
    return sorted(out, reverse=True)[:n]


def main():
    with open(STATE, encoding="utf-8") as f:
        state = json.load(f)
    only = [c.upper() for c in sys.argv[1:]]
    orders = get("/v5/order/realtime", {"category": "spot"}).get("result", {}).get("list", []) or []

    for coin, p in state["positions"].items():
        if p.get("status") != "rebuy":
            continue
        if only and coin not in only:
            continue
        sym = p["symbol"]
        budget = float(p.get("budget", p.get("spent_usdt", 10)))
        last = float(pub("/v5/market/tickers", {"category": "spot", "symbol": sym})["result"]["list"][0]["lastPrice"])

        # снять старые откупные
        for o in orders:
            if o["symbol"] == sym and o["side"] == "Buy":
                post("/v5/order/cancel", {"category": "spot", "symbol": sym, "orderId": o["orderId"]})
                print(f"{coin}: снял старый откуп {o['qty']}@{o['price']}")

        # уровни и доли: 3 уровня 40/35/25; если бюджет < $16 — 2 уровня 55/45
        if budget >= 16:
            levels = support_levels(sym, last, 3)
            shares = [0.40, 0.35, 0.25]
        else:
            levels = support_levels(sym, last, 2)
            shares = [0.55, 0.45]

        placed = []
        for lvl, sh in zip(levels, shares):
            usd = budget * sh
            if usd < 5:  # мин. ордер
                continue
            pr = fmt_price(sym, lvl)
            qty = fmt_qty(sym, usd / float(pr))
            r = spot_order(sym, "Buy", "Limit", qty, price=pr)
            ok = r.get("retCode") == 0
            placed.append((pr, qty, usd, ok, r.get("retMsg")))
            print(f"{coin}: уровень {pr} ({(float(pr)/last-1)*100:+.1f}%) — {qty} шт (~${usd:.2f}) -> {'OK' if ok else r.get('retMsg')}")

        if placed:
            p["rebuy_price"] = float(placed[0][0])  # верхний уровень — референс для алертов
            p.pop("runaway_alerted", None)

    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    print("positions.json обновлён")


if __name__ == "__main__":
    main()
