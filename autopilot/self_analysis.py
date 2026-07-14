# -*- coding: utf-8 -*-
"""Самоанализ: реализованная прибыль по монетам из истории исполнений Bybit (FIFO).
Считает по каждой монете: сколько циклов (продаж), винрейт, чистую прибыль, комиссии,
текущую незакрытую позицию. Дайджест — в Telegram. Так бот «учится» на своих сделках."""
import os
import sys
import time
from collections import defaultdict, deque

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
from bybit_client import get
from tg import send


def fetch_executions(days=7):
    """Все спот-исполнения за N дней (с пагинацией)."""
    end = int(time.time() * 1000)
    start = end - days * 24 * 3600 * 1000
    out, cursor = [], ""
    for _ in range(20):  # до 20 страниц
        params = {"category": "spot", "limit": "100", "startTime": str(start), "endTime": str(end)}
        if cursor:
            params["cursor"] = cursor
        r = get("/v5/execution/list", params)
        if r.get("retCode") != 0:
            break
        res = r.get("result", {})
        out += res.get("list", [])
        cursor = res.get("nextPageCursor") or ""
        if not cursor:
            break
    return out


def analyze(days=7):
    execs = fetch_executions(days)
    by_sym = defaultdict(list)
    for e in execs:
        by_sym[e["symbol"]].append(e)

    report = {}
    for sym, lst in by_sym.items():
        lst.sort(key=lambda x: int(x["execTime"]))  # хронологически
        lots = deque()  # очередь покупок: [qty, price]
        realized = 0.0      # реализованная прибыль USDT
        fees = 0.0          # комиссии USDT
        sells = 0           # число продаж (фиксаций)
        wins = 0            # прибыльных продаж
        for e in lst:
            price = float(e["execPrice"])
            qty = float(e["execQty"])
            fee = float(e["execFee"])
            fee_usdt = fee * price if e.get("feeCurrency") != "USDT" else fee  # комиссия покупки в монете → в USDT
            fees += fee_usdt
            if e["side"] == "Buy":
                lots.append([qty, price])
            else:  # Sell — матчим FIFO против покупок
                sells += 1
                q = qty
                cost = 0.0
                matched = 0.0
                while q > 1e-12 and lots:
                    lot = lots[0]
                    take = min(q, lot[0])
                    cost += take * lot[1]
                    matched += take
                    lot[0] -= take
                    q -= take
                    if lot[0] <= 1e-12:
                        lots.popleft()
                proceeds = matched * price
                profit = proceeds - cost
                realized += profit
                if profit > 0:
                    wins += 1
        # незакрытая позиция
        held_qty = sum(l[0] for l in lots)
        held_cost = sum(l[0] * l[1] for l in lots)
        avg = held_cost / held_qty if held_qty > 1e-9 else 0
        report[sym] = {
            "realized": realized - fees,  # чистая (за вычетом комиссий)
            "gross": realized, "fees": fees,
            "sells": sells, "wins": wins,
            "held_qty": held_qty, "avg": avg,
        }
    return report


def fmt(days=7):
    r = analyze(days)
    if not r:
        return "📊 Самоанализ: сделок за период нет."
    total = sum(v["realized"] for v in r.values())
    ranked = sorted(r.items(), key=lambda kv: kv[1]["realized"], reverse=True)
    lines = [f"📊 <b>Самоанализ за {days} дн.</b> (реальные сделки с биржи)", ""]
    lines.append(f"{'🟢' if total >= 0 else '🔴'} Чистая реализованная прибыль: <b>{total:+.2f} USDT</b>")
    lines.append("")
    for sym, v in ranked:
        coin = sym.replace("USDT", "")
        wr = (v["wins"] / v["sells"] * 100) if v["sells"] else 0
        icon = "🟢" if v["realized"] >= 0 else "🔴"
        lines.append(f"{icon} <b>{coin}</b>: {v['realized']:+.2f} USDT | циклов {v['sells']}, винрейт {wr:.0f}%")
        lines.append(f"    комиссии {v['fees']:.2f} · держим {v['held_qty']:.3g} по ~{v['avg']:.4g}")
    # инсайт
    best = ranked[0]
    worst = ranked[-1]
    lines.append("")
    if best[1]["realized"] > 0:
        lines.append(f"⭐ Лучший: {best[0].replace('USDT','')} (+{best[1]['realized']:.2f}). "
                     f"Грид крутится бодрее всего.")
    if worst[1]["realized"] < 0 or worst[1]["sells"] == 0:
        wc = worst[0].replace("USDT", "")
        lines.append(f"🐌 Буксует: {wc} — мало циклов/в минусе. Возможно, стоит на него меньше опираться.")
    return "\n".join(lines)


if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    msg = fmt(days)
    print(msg)
    send(msg)
