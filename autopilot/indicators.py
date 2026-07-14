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
