# -*- coding: utf-8 -*-
"""Индикаторы на чистом Python (без pandas): ATR, RSI, EMA, SMA.
Данные — свечи Bybit (см. levels.klines: [o,h,l,c], новые первыми).
Формулы соответствуют скиллам exit-strategies/pandas-ta (Wilder smoothing)."""


def _chrono(candles):
    """Свечи от старых к новым."""
    return list(reversed(candles))


def atr(candles, length=14):
    """Average True Range (Wilder). candles: [[o,h,l,c], ...] новые первыми."""
    c = _chrono(candles)
    trs = []
    for i in range(1, len(c)):
        h, l, pc = c[i][1], c[i][2], c[i - 1][3]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if len(trs) < length:
        return None
    a = sum(trs[:length]) / length
    for tr in trs[length:]:
        a = (a * (length - 1) + tr) / length
    return a


def rsi(candles, length=14):
    """RSI (Wilder). >70 перекуплен, <30 перепродан."""
    closes = [x[3] for x in _chrono(candles)]
    if len(closes) < length + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    ag = sum(gains[:length]) / length
    al = sum(losses[:length]) / length
    for i in range(length, len(gains)):
        ag = (ag * (length - 1) + gains[i]) / length
        al = (al * (length - 1) + losses[i]) / length
    if al == 0:
        return 100.0
    return 100 - 100 / (1 + ag / al)


def ema(candles, length=20):
    closes = [x[3] for x in _chrono(candles)]
    if len(closes) < length:
        return None
    e = sum(closes[:length]) / length
    k = 2 / (length + 1)
    for p in closes[length:]:
        e = p * k + e * (1 - k)
    return e


def sma(candles, length=20):
    closes = [x[3] for x in _chrono(candles)]
    if len(closes) < length:
        return None
    return sum(closes[-length:]) / length


def atr_stop(entry, candles, mult=2.0, length=14):
    """Стоп по ATR: entry - ATR*mult (рекомендация exit-strategies)."""
    a = atr(candles, length)
    return entry - a * mult if a else None


def chandelier_trailing(candles, mult=3.0, length=14, lookback=22):
    """Chandelier exit: max(high, lookback) - ATR*mult — трейлинг для сильного тренда."""
    c = _chrono(candles)
    a = atr(candles, length)
    if not a or len(c) < lookback:
        return None
    highest = max(x[1] for x in c[-lookback:])
    return highest - a * mult


def adx(candles, length=14):
    """ADX (Wilder) — сила тренда. <20 флэт, 20-40 тренд, >40 сильный тренд.
    Не путать с направлением: ADX высокий и в росте, и в падении."""
    c = _chrono(candles)
    if len(c) < length * 2 + 1:
        return None
    plus_dm, minus_dm, trs = [], [], []
    for i in range(1, len(c)):
        up = c[i][1] - c[i - 1][1]      # high - prev high
        down = c[i - 1][2] - c[i][2]    # prev low - low
        plus_dm.append(up if (up > down and up > 0) else 0.0)
        minus_dm.append(down if (down > up and down > 0) else 0.0)
        h, l, pc = c[i][1], c[i][2], c[i - 1][3]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))

    def _smooth(arr):
        s = sum(arr[:length])
        out = [s]
        for x in arr[length:]:
            s = s - s / length + x
            out.append(s)
        return out

    str_ = _smooth(trs)
    pdm_s = _smooth(plus_dm)
    mdm_s = _smooth(minus_dm)
    dx = []
    for i in range(len(str_)):
        if str_[i] == 0:
            continue
        pdi = 100 * pdm_s[i] / str_[i]
        mdi = 100 * mdm_s[i] / str_[i]
        denom = pdi + mdi
        dx.append(100 * abs(pdi - mdi) / denom if denom else 0.0)
    if len(dx) < length:
        return None
    a = sum(dx[:length]) / length
    for x in dx[length:]:
        a = (a * (length - 1) + x) / length
    return a


# ============ Расширенный набор (14.07.2026) ============

def _closes(candles):
    return [x[3] for x in _chrono(candles)]


def sma_of(vals, length):
    return sum(vals[-length:]) / length if len(vals) >= length else None


def bollinger(candles, length=20, mult=2.0):
    """Полосы Боллинджера. Возвращает upper/mid/lower и %b (0=нижняя,1=верхняя).
    %b<0 — пробой вниз (перепродан), >1 — пробой вверх (перекуплен)."""
    closes = _closes(candles)
    if len(closes) < length:
        return None
    w = closes[-length:]
    mid = sum(w) / length
    sd = (sum((c - mid) ** 2 for c in w) / length) ** 0.5
    upper, lower = mid + mult * sd, mid - mult * sd
    last = closes[-1]
    pctb = (last - lower) / (upper - lower) if upper != lower else 0.5
    return {"upper": upper, "mid": mid, "lower": lower, "pctb": pctb}


def _ema_series(vals, length):
    if len(vals) < length:
        return []
    k = 2 / (length + 1)
    e = sum(vals[:length]) / length
    out = [e]
    for v in vals[length:]:
        e = v * k + e * (1 - k)
        out.append(e)
    return out


def macd(candles, fast=12, slow=26, signal=9):
    """MACD. hist>0 и растёт — бычий импульс; пересечение сигнальной — разворот импульса."""
    closes = _closes(candles)
    if len(closes) < slow + signal:
        return None
    ef, es = _ema_series(closes, fast), _ema_series(closes, slow)
    ef = ef[len(ef) - len(es):]  # выравниваем хвосты
    macd_line = [a - b for a, b in zip(ef, es)]
    sig = _ema_series(macd_line, signal)
    if not sig:
        return None
    return {"macd": macd_line[-1], "signal": sig[-1], "hist": macd_line[-1] - sig[-1]}


def stochastic(candles, k_len=14, d_len=3):
    """Стохастик %K/%D. >80 перекуплен, <20 перепродан."""
    c = _chrono(candles)
    if len(c) < k_len + d_len:
        return None
    ks = []
    for i in range(k_len - 1, len(c)):
        w = c[i - k_len + 1:i + 1]
        hh = max(x[1] for x in w)
        ll = min(x[2] for x in w)
        close = c[i][3]
        ks.append(100 * (close - ll) / (hh - ll) if hh != ll else 50)
    return {"k": ks[-1], "d": sum(ks[-d_len:]) / d_len}


def parabolic_sar(candles, step=0.02, mx=0.2):
    """Parabolic SAR — трейлинг-стоп по тренду. Возвращает уровень SAR и направление."""
    c = _chrono(candles)
    if len(c) < 5:
        return None
    up = c[1][3] >= c[0][3]
    sar = c[0][2] if up else c[0][1]
    ep = c[0][1] if up else c[0][2]
    af = step
    for i in range(1, len(c)):
        sar = sar + af * (ep - sar)
        hi, lo = c[i][1], c[i][2]
        if up:
            if lo < sar:
                up, sar, ep, af = False, ep, lo, step
            elif hi > ep:
                ep, af = hi, min(af + step, mx)
        else:
            if hi > sar:
                up, sar, ep, af = True, ep, hi, step
            elif lo < ep:
                ep, af = lo, min(af + step, mx)
    return {"sar": sar, "trend": "up" if up else "down"}
