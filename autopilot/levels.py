# -*- coding: utf-8 -*-
"""Уровни поддержки/сопротивления по свечам Bybit (свинги 1h/4h/1D + пивоты)."""
import sys

from bybit_client import pub


def klines(symbol, interval, limit):
    r = pub("/v5/market/kline", {"category": "spot", "symbol": symbol, "interval": interval, "limit": str(limit)})
    return [[float(x) for x in c[1:5]] for c in r["result"]["list"]]  # [o,h,l,c], новые первыми


def swings(candles, wing=3):
    highs, lows = [], []
    for i in range(wing, len(candles) - wing):
        h, l = candles[i][1], candles[i][2]
        if all(h >= candles[j][1] for j in range(i - wing, i + wing + 1)):
            highs.append(h)
        if all(l <= candles[j][2] for j in range(i - wing, i + wing + 1)):
            lows.append(l)
    return highs, lows


def pivots(symbol):
    d = klines(symbol, "D", 3)
    o, h, l, c = d[1]
    p = (h + l + c) / 3
    return {"P": p, "R1": 2 * p - l, "R2": p + (h - l), "S1": 2 * p - h, "S2": p - (h - l)}


def nearest_support(symbol, last):
    """Самая высокая поддержка в коридоре -3.5%..-0.8% от текущей; нет — -2%."""
    cands = []
    for tf, lim, wing in [("60", 168, 3), ("240", 180, 3)]:
        _, ls = swings(klines(symbol, tf, lim), wing)
        cands += ls
    pv = pivots(symbol)
    cands += [pv["S1"], pv["P"]]
    inr = [s for s in cands if last * 0.965 <= s <= last * 0.992]
    return max(inr) if inr else last * 0.98


def nearest_resistance(symbol, last):
    """Ближайшее сопротивление в коридоре +0.8%..+3.5%, TP чуть ниже него; нет — +1.5%."""
    cands = []
    for tf, lim, wing in [("60", 168, 3), ("240", 180, 3), ("D", 90, 2)]:
        hs, _ = swings(klines(symbol, tf, lim), wing)
        cands += hs
    pv = pivots(symbol)
    cands += [pv["R1"], pv["R2"]]
    inr = [r for r in cands if last * 1.008 <= r <= last * 1.035]
    return (min(inr) if inr else last * 1.015) * 0.998
