# -*- coding: utf-8 -*-
"""Отчёт по запросу (команда «отчет» в боте): полное состояние дел."""
import json
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
from bybit_client import balances, get, pub
from fng import label as fng_label
from tg import send


def main():
    with open(os.path.join(BASE, "positions.json"), encoding="utf-8") as f:
        state = json.load(f)
    bal = balances()

    lines = [f"📋 <b>Отчёт по запросу</b>", ""]
    lines.append(f"💼 Баланс: <b>{bal['totalEquity']:.2f} USD</b> (старт {state['start_equity']:.2f})")
    pnl = bal["totalEquity"] - state["start_equity"]
    lines.append(f"{'🟢' if pnl >= 0 else '🔴'} Прибыль с начала: {pnl:+.2f} USD ({pnl / state['start_equity'] * 100:+.1f}%)")
    lines.append("")

    orders = get("/v5/order/realtime", {"category": "spot"}).get("result", {}).get("list", []) or []
    by_sym = {}
    for o in orders:
        by_sym.setdefault(o["symbol"], []).append(o)

    for coin, p in state["positions"].items():
        sym = p["symbol"]
        held = bal.get(coin, {}).get("qty", 0)
        last = float(pub("/v5/market/tickers", {"category": "spot", "symbol": sym})["result"]["list"][0]["lastPrice"])
        if p.get("status") == "rebuy":
            lines.append(f"⏳ {coin}: продано с прибылью, жду отката до {p.get('rebuy_price', 0):.4g}, "
                         f"чтобы купить обратно (сейчас {last:.4g})")
        else:
            chg = (last / p["entry"] - 1) * 100
            icon = "🟢" if chg >= 0 else "🔴"
            lines.append(f"{icon} {coin}: {held:.3f} шт, куплено по {p['entry']:.4g}, сейчас {last:.4g} ({chg:+.1f}%)")
            lines.append(f"    ↳ продам по {p['tp']:.4g} → будет {(p['tp'] / p['entry'] - 1) * 100:+.1f}% прибыли")

    lines.append(f"\n💵 Свободные USDT: {bal.get('USDT', {}).get('qty', 0):.2f}")
    lines.append(f"📌 Активных заявок на бирже: {len(orders)}")
    mood = fng_label()
    if mood:
        lines.append(f"🌡 Настроение рынка: {mood}")
    send("\n".join(lines))


if __name__ == "__main__":
    main()
