# -*- coding: utf-8 -*-
"""Ежечасный крон на Beget: грид-цикл + отчёт + алерты. Детерминированный, без ИИ.

Цикл по каждой позиции:
  holding: TP исполнился -> лимитный откуп у ближайшей поддержки (-0.8..-3.5%)
  rebuy:   откуп исполнился -> новый TP чуть ниже ближайшего сопротивления (+0.8..+3.5%)
Плюс: восстановление пропавших ордеров, алерты о просадке -8% (решает Ильдар/Claude).
"""
import json
import math
import os
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
from bybit_client import balances, get, instrument, post, pub, spot_order
from levels import klines, nearest_resistance, nearest_support
from indicators import adx, chandelier_trailing, ema, rsi
from fng import dip_multiplier, label as fng_label
from tg import send

STATE_FILE = os.path.join(BASE, "positions.json")
LOG_FILE = os.path.join(BASE, "trade_log.txt")
ALERT_DIP = -5.0            # порог усреднения (было -8): чаще ловим откаты
TRAIL_RSI = 62             # если у сопротивления RSI4h выше — тренд силён, ведём тейк вверх
TRAIL_NEAR = 0.006        # «подходит к тейку»: цена в пределах 0.6% ниже TP


def log(msg):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")


def fmt_qty(symbol, qty):
    bp = instrument(symbol)["lotSizeFilter"]["basePrecision"]
    dec = len(bp.split(".")[1]) if "." in bp else 0
    return f"{math.floor(qty / float(bp)) * float(bp):.{dec}f}"


def fmt_price(symbol, price):
    tick = instrument(symbol)["priceFilter"]["tickSize"]
    dec = len(tick.split(".")[1]) if "." in tick else 0
    return f"{math.floor(price / float(tick)) * float(tick):.{dec}f}"


def last_price(symbol):
    return float(pub("/v5/market/tickers", {"category": "spot", "symbol": symbol})["result"]["list"][0]["lastPrice"])


def main():
    paused = os.path.exists(os.path.join(BASE, "PAUSED"))
    with open(STATE_FILE, encoding="utf-8") as f:
        state = json.load(f)
    bal = balances()
    orders = get("/v5/order/realtime", {"category": "spot"}).get("result", {}).get("list", []) or []
    by_sym = {}
    for o in orders:
        by_sym.setdefault(o["symbol"], []).append(o)

    actions, alerts, plines = [], [], []
    _dip_mult = dip_multiplier()  # множитель агрессии докупки по Fear&Greed

    for coin, p in state["positions"].items():
        sym = p["symbol"]
        held_qty = bal.get(coin, {}).get("qty", 0)
        held_usd = bal.get(coin, {}).get("usd", 0)
        sells = [o for o in by_sym.get(sym, []) if o["side"] == "Sell"]
        buys = [o for o in by_sym.get(sym, []) if o["side"] == "Buy"]
        last = last_price(sym)
        status = p.get("status", "holding")

        if paused:
            pass  # автоторговля на паузе — только отчёт, без сделок
        elif status == "holding":
            if held_usd < 1.0 and not sells and buys:
                # ИДЕМПОТЕНТНОСТЬ (#6): откуп уже висит, но статус не сохранился на прошлом тике
                # (сбой между ордером и записью). НЕ ставим второй ордер — чиним статус.
                p["status"] = "rebuy"
                p.setdefault("budget", round(p["qty"] * p["tp"] * 0.999, 4))
                p["rebuy_price"] = float(buys[0]["price"])
                log(f"{coin} REBUY_RECONCILED (ордер уже был) @ {buys[0]['price']}")
            elif held_usd < 1.0 and not sells:
                # TP исполнился -> откуп у поддержки
                profit_pct = (p["tp"] / p["entry"] - 1) * 100
                proceeds = p["qty"] * p["tp"] * 0.999
                target = nearest_support(sym, last)
                qty_str = fmt_qty(sym, proceeds / target)
                pr_str = fmt_price(sym, target)
                r = spot_order(sym, "Buy", "Limit", qty_str, price=pr_str)
                if r.get("retCode") == 0:
                    p["status"] = "rebuy"
                    p["budget"] = round(proceeds, 4)
                    p["rebuy_price"] = float(pr_str)
                    profit_usd = proceeds - p.get("spent_usdt", proceeds)
                    actions.append(
                        f"💰 <b>{coin}: зафиксировал прибыль!</b>\n"
                        f"Продал {p['qty']:.3f} шт по {p['tp']:.4g} → +{profit_usd:.2f}$ ({profit_pct:+.1f}%).\n"
                        f"Теперь жду отката вниз, чтобы купить дешевле: заявка на {qty_str} шт по {pr_str}.\n"
                        f"Если купится — монет будет больше на те же деньги.")
                    log(f"{coin} TP_FILLED {p['tp']} -> REBUY {qty_str}@{pr_str}")
                else:
                    alerts.append(f"{coin}: TP сработал, но откуп не выставился: {r.get('retMsg')}")
            elif held_usd >= 1.0 and not sells:
                # монета есть, тейка нет — восстановить
                tp = float(fmt_price(sym, nearest_resistance(sym, last)))
                r = spot_order(sym, "Sell", "Limit", fmt_qty(sym, held_qty), price=fmt_price(sym, tp))
                if r.get("retCode") == 0:
                    p["tp"] = tp
                    actions.append(f"♻️ {coin}: у позиции не было заявки на продажу — поставил новую: "
                                   f"продам по {tp:.4g} (это {(tp / p['entry'] - 1) * 100:+.1f}% к цене покупки)")
                    log(f"{coin} TP_RESTORED {tp}")
            elif held_usd >= 1.0 and sells:
                # ТРЕЙЛИНГ: цена подошла к тейку на сильном тренде — ведём тейк выше, не продаём
                near_tp = last >= p["tp"] * (1 - TRAIL_NEAR)
                strong = rsi(klines(sym, "240", 100)) >= TRAIL_RSI
                trail = chandelier_trailing(klines(sym, "240", 100))
                if near_tp and strong and trail and trail > p["tp"]:
                    new_tp = float(fmt_price(sym, max(nearest_resistance(sym, last), trail)))
                    if new_tp > p["tp"] * 1.003:  # двигаем только на заметный шаг
                        o = sells[0]
                        post("/v5/order/cancel", {"category": "spot", "symbol": sym, "orderId": o["orderId"]})
                        r = spot_order(sym, "Sell", "Limit", fmt_qty(sym, held_qty), price=fmt_price(sym, new_tp))
                        if r.get("retCode") == 0:
                            old = p["tp"]
                            p["tp"] = new_tp
                            actions.append(f"📈 <b>{coin}: тренд сильный — не жадничаю наоборот!</b>\n"
                                           f"Цена подошла к {old:.4g}, но растёт бодро (RSI высокий). "
                                           f"Поднял цель продажи до {new_tp:.4g}, чтобы забрать больше.")
                            log(f"{coin} TRAIL {old} -> {new_tp}")
        else:  # rebuy
            if held_usd >= 1.0:
                # откуп исполнился -> новый TP
                entry = p["budget"] / held_qty if held_qty > 0 else p.get("rebuy_price", last)
                tp = float(fmt_price(sym, nearest_resistance(sym, last)))
                r = spot_order(sym, "Sell", "Limit", fmt_qty(sym, held_qty), price=fmt_price(sym, tp))
                if r.get("retCode") == 0:
                    p.update(qty=held_qty, entry=round(entry, 6), tp=tp,
                             spent_usdt=p.get("budget", held_usd), status="holding")
                    p.pop("rebuy_price", None)
                    actions.append(
                        f"🛒 <b>{coin}: купил обратно дешевле!</b>\n"
                        f"Взял {held_qty:.3f} шт по ~{entry:.4g}.\n"
                        f"Новая цель: продам по {tp:.4g}, будет ещё {(tp / entry - 1) * 100:+.1f}% прибыли.")
                    log(f"{coin} REBOUGHT {held_qty}@{entry} TP {tp}")
                else:
                    alerts.append(f"{coin}: откуплено, но TP не выставился: {r.get('retMsg')}")
            elif not buys:
                # ордера на откуп нет и монеты нет — восстановить откуп
                target = nearest_support(sym, last)
                budget = p.get("budget", p.get("spent_usdt", 5))
                qty_str = fmt_qty(sym, budget / target)
                pr_str = fmt_price(sym, target)
                r = spot_order(sym, "Buy", "Limit", qty_str, price=pr_str)
                if r.get("retCode") == 0:
                    p["rebuy_price"] = float(pr_str)
                    actions.append(f"♻️ {coin}: заявка на обратную покупку пропала — выставил заново: {qty_str} шт по {pr_str}")
                    log(f"{coin} REBUY_RESTORED {qty_str}@{pr_str}")
            else:
                # откуп висит; если цена убежала вверх >3.5% от лимитки — алерт
                if last > p.get("rebuy_price", last) * 1.035:
                    alerts.append(f"{coin}: продали, ждём отката для обратной покупки по {p['rebuy_price']:.4g}, "
                                  f"но цена ушла вверх на {(last / p['rebuy_price'] - 1) * 100:+.1f}% и не падает. Нужно решение: догонять или ждать")

        # строка отчёта
        if p.get("status") == "rebuy":
            plines.append(f"⏳ {coin}: продано с прибылью, жду отката до {p.get('rebuy_price', 0):.4g}, чтобы купить обратно (сейчас цена {last:.4g})")
        else:
            chg = (last / p["entry"] - 1) * 100
            tp_pct = (p["tp"] / p["entry"] - 1) * 100
            icon = "🟢" if chg >= 0 else "🔴"
            plines.append(f"{icon} {coin}: {held_qty:.3f} шт, куплено по {p['entry']:.4g}, сейчас {last:.4g} ({chg:+.1f}%)")
            plines.append(f"    ↳ продам по {p['tp']:.4g} → будет {tp_pct:+.1f}% прибыли")
            # порог усреднения плавает по настроению рынка: страх → докупаем раньше
            dip_threshold = ALERT_DIP / _dip_mult
            if chg > dip_threshold:
                p.pop("dip_alerted", None)  # цена выше порога — сброс, следующий провал уведомит заново
            elif not p.get("dip_alerted"):  # уведомляем ОДИН раз за падение, без спама каждый тик
                p["dip_alerted"] = True
                mood = " (рынок в страхе — хорошая точка!)" if _dip_mult > 1.1 else ""
                free = bal.get("USDT", {}).get("qty", 0)
                buy_amt = min(6, round(free, 2))
                # ADX-фильтр (из стратегии Vega): не усредняем на сильном падающем тренде
                k4 = klines(sym, "240", 120)
                trend_strength = adx(k4) or 0
                ema20 = ema(k4, 20) or last
                strong_downtrend = trend_strength >= 40 and last < ema20
                if strong_downtrend:
                    alerts.append(f"{coin} подешевел на {chg:.1f}%, НО это сильный тренд вниз "
                                  f"(ADX {trend_strength:.0f}) — усреднять опасно, можно ловить нож. "
                                  f"Жду замедления падения, докупку придержал.")
                elif buy_amt >= 5:
                    # заготавливаем действие: ответишь «да» в боте — докупит сразу
                    with open(os.path.join(BASE, "pending.json"), "w", encoding="utf-8") as pf:
                        json.dump({"ts": int(time.time()),
                                   "question": f"докупить {coin} на ${buy_amt}",
                                   "action": {"type": "buy", "symbol": sym, "coin": coin, "usdt": buy_amt}}, pf)
                    alerts.append(f"{coin} подешевел на {chg:.1f}% от покупки{mood}, тренд спокойный "
                                  f"(ADX {trend_strength:.0f}).\nДокупить на ${buy_amt}? Ответь «да» или «нет» 👇")
                else:
                    alerts.append(f"{coin} подешевел на {chg:.1f}% от покупки{mood}, но свободных USDT мало (${free:.2f}).")

    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

    # отчёт: тихий режим — шлём только при событиях или в плановые сводки
    # (08:02 и 19:02 по Бишкеку = 05 и 16 по серверному МСК)
    now = time.localtime()
    # самоанализ КАЖДЫЕ 3 ДНЯ в 21:00 Бишкек (18:00 сервер МСК), первый тик часа
    if now.tm_yday % 3 == 0 and now.tm_hour == 18 and now.tm_min < 15:
        try:
            from self_analysis import fmt as _analysis
            send(_analysis(3))
            log("3-day self-analysis sent")
        except Exception as e:
            log(f"analysis error: {e}")
    scheduled_summary = now.tm_hour in (5, 16) and now.tm_min < 5  # только первый тик часа, чтобы сводка не дублировалась при любом ритме (5/15/30 мин)
    if not (actions or alerts or scheduled_summary):
        log(f"heartbeat equity={bal['totalEquity']:.2f} (тихо, событий нет)")
        print(time.strftime("%H:%M") + f" heartbeat equity={bal['totalEquity']:.2f}")  # в cron.log для контроля живости
        return
    lines = [f"💼 <b>Баланс: {bal['totalEquity']:.2f} USD</b> (старт {state['start_equity']:.2f})"]
    if paused:
        lines.insert(0, "⏸ <b>НА ПАУЗЕ</b> (напиши «старт» для продолжения)\n")
    pnl = bal["totalEquity"] - state["start_equity"]
    lines.append(f"{'🟢' if pnl >= 0 else '🔴'} P&L с начала: {pnl:+.2f} USD ({pnl / state['start_equity'] * 100:+.1f}%)")
    lines.append("")
    lines += plines
    lines.append(f"\n💵 Резерв USDT: {bal.get('USDT', {}).get('qty', 0):.2f}")
    mood = fng_label()
    if mood:
        lines.append(f"🌡 Настроение рынка: {mood}")
    if actions:
        lines.append("\n⚡ <b>ДЕЙСТВИЯ:</b>\n" + "\n".join(actions))
    if alerts:
        lines.append("\n⚠️ <b>АЛЕРТЫ:</b>\n" + "\n".join("• " + a for a in alerts))
    send("\n".join(lines))


if __name__ == "__main__":
    main()
