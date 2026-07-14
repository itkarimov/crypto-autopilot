# -*- coding: utf-8 -*-
"""Fear & Greed Index (alternative.me, бесплатно). Настроение рынка 0-100.
0-25 крайний страх, 25-45 страх, 45-55 нейтрально, 55-75 жадность, 75-100 крайняя жадность."""
import json
import urllib.request


def get_fng():
    """Возвращает (value:int, classification:str) или (None, None) при ошибке."""
    try:
        with urllib.request.urlopen("https://api.alternative.me/fng/?limit=1", timeout=15) as r:
            d = json.loads(r.read().decode())["data"][0]
        return int(d["value"]), d["value_classification"]
    except Exception:
        return None, None


def dip_multiplier():
    """Множитель агрессии докупки по настроению рынка.
    Крайний страх → докупаем смелее (рынок на дне), жадность → осторожнее."""
    v, _ = get_fng()
    if v is None:
        return 1.0
    if v <= 25:   # крайний страх — лучшие точки входа
        return 1.5
    if v <= 45:   # страх
        return 1.2
    if v >= 75:   # крайняя жадность — почти не докупаем
        return 0.5
    if v >= 55:   # жадность
        return 0.8
    return 1.0    # нейтрально


def label():
    """Строка для отчётов, напр. '😱 Страх (26/100)'."""
    v, c = get_fng()
    if v is None:
        return ""
    emoji = "😱" if v <= 25 else "😟" if v <= 45 else "😐" if v < 55 else "🤑" if v < 75 else "🤪"
    ru = {"Extreme Fear": "Крайний страх", "Fear": "Страх", "Neutral": "Нейтрально",
          "Greed": "Жадность", "Extreme Greed": "Крайняя жадность"}.get(c, c)
    return f"{emoji} {ru} ({v}/100)"


if __name__ == "__main__":
    print(label(), "| множитель докупки:", dip_multiplier())
