# -*- coding: utf-8 -*-
"""Обработчик ответов из Telegram-бота (вызывается webhook.php).
Понимает: да/нет на висящий вопрос (pending.json), прямые команды (докупи/продай/стоп/старт).
Аргумент: текст сообщения владельца."""
import json
import math
import os
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
from bybit_client import balances, instrument, spot_order
from fng import label as fng_label
from tg import send

PENDING = os.path.join(BASE, "pending.json")
INBOX = os.path.join(BASE, "inbox.txt")
PAUSED = os.path.join(BASE, "PAUSED")
STATE = os.path.join(BASE, "positions.json")
LOG = os.path.join(BASE, "trade_log.txt")

WHITELIST = {"SOL": "SOLUSDT", "LINK": "LINKUSDT", "UNI": "UNIUSDT", "ETH": "ETHUSDT",
             "XRP": "XRPUSDT", "LTC": "LTCUSDT", "AVAX": "AVAXUSDT", "DOT": "DOTUSDT",
             "ADA": "ADAUSDT", "NEAR": "NEARUSDT", "AAVE": "AAVEUSDT"}
YES = {"да", "давай", "ага", "докупить", "докупи", "купи", "покупай", "ок", "окей", "+", "го", "yes"}
NO = {"нет", "не", "не надо", "ждать", "жди", "отмена", "стоп", "-", "no", "пропусти"}


def log(m):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + m + "\n")


def fmt_qty(sym, qty):
    bp = instrument(sym)["lotSizeFilter"]["basePrecision"]
    d = len(bp.split(".")[1]) if "." in bp else 0
    return f"{math.floor(qty / float(bp)) * float(bp):.{d}f}"


MANUAL_BUY_CAP = 20.0  # потолок на ручную покупку без доп-подтверждения (защита от опечатки)


def do_buy(sym, coin, usdt):
    bal = balances()
    free = bal.get("USDT", {}).get("qty", 0)
    if usdt > MANUAL_BUY_CAP:
        send(f"⚠️ Заказ на {coin} ${usdt:.0f} превышает лимит ручной покупки ${MANUAL_BUY_CAP:.0f}. "
             f"Если сумма верная — напиши «докупи {coin} {MANUAL_BUY_CAP:.0f}» частями или подтверди отдельно. "
             f"(Защита от опечатки.)")
        return
    usdt = min(usdt, free)
    if usdt < 5:
        send(f"❌ Не могу купить {coin}: свободных USDT только {free:.2f} (мин. ордер $5).")
        return
    r = spot_order(sym, "Buy", "Market", str(round(usdt, 2)))
    if r.get("retCode") == 0:
        log(f"MANUAL BUY {coin} ${usdt:.2f}")
        send(f"✅ Купил {coin} на ${usdt:.2f} по рынку. Механика на след. цикле поставит тейк.")
    else:
        send(f"❌ Ошибка покупки {coin}: {r.get('retMsg')}")


def do_sell(sym, coin):
    bal = balances()
    qty = bal.get(coin, {}).get("qty", 0)
    if qty <= 0:
        send(f"❌ {coin} нет на счету.")
        return
    r = spot_order(sym, "Sell", "Market", fmt_qty(sym, qty))
    if r.get("retCode") == 0:
        log(f"MANUAL SELL {coin} all")
        send(f"✅ Продал весь {coin} по рынку.")
    else:
        send(f"❌ Ошибка продажи {coin}: {r.get('retMsg')}")


def clear_pending():
    if os.path.exists(PENDING):
        os.remove(PENDING)


QUEUE = os.path.join(BASE, "bot_queue.txt")


def _read_input():
    """Текст сообщения. --queue: последняя строка из очереди (webhook пишет туда UTF-8,
    минуя shell — иначе escapeshellarg на Beget режет кириллицу). Иначе — из argv (fallback)."""
    if len(sys.argv) >= 2 and sys.argv[1] == "--queue":
        if not os.path.exists(QUEUE):
            return ""
        with open(QUEUE, encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]
        open(QUEUE, "w").close()  # очищаем очередь
        return lines[-1] if lines else ""
    if len(sys.argv) >= 3 and sys.argv[1] == "--file":
        path = sys.argv[2]
        try:
            with open(path, encoding="utf-8") as f:
                raw = f.read().strip()
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
        return raw
    return " ".join(sys.argv[1:]).strip()


def main():
    raw = _read_input()
    text = raw.lower()
    if not text:
        return
    words = text.split()

    # 1. Ответ на висящий вопрос
    pending = None
    if os.path.exists(PENDING):
        try:
            pending = json.load(open(PENDING, encoding="utf-8"))
            if time.time() - pending.get("ts", 0) > 7200:  # вопрос протух за 2ч
                pending = None
                clear_pending()
        except Exception:
            pending = None

    if pending and (words[0] in YES or words[0] in NO):
        if words[0] in YES:
            a = pending.get("action", {})
            if a.get("type") == "buy":
                do_buy(a["symbol"], a["coin"], a.get("usdt", 6))
            elif a.get("type") == "sell":
                do_sell(a["symbol"], a["coin"])
            else:
                send("✅ Принял «да», но действие уже неактуально.")
        else:
            send("👌 Понял, ничего не делаю — жду дальше.")
        clear_pending()
        return

    # 2. Управление паузой
    if words[0] in ("стоп", "пауза", "pause"):
        open(PAUSED, "w").close()
        send("⏸ Автоторговля на паузе. Позиции и заявки на бирже остаются. Напиши «старт», чтобы продолжить.")
        return
    if words[0] in ("старт", "продолжай", "resume", "старт!"):
        if os.path.exists(PAUSED):
            os.remove(PAUSED)
        send("▶️ Автоторговля снова активна.")
        return

    # 3. Прямые команды: докупи/купи <COIN> [сумма], продай <COIN>
    coin = next((c for c in WHITELIST if c.lower() in words), None)
    if words[0] in ("докупи", "купи", "докупить", "buy") and coin:
        amt = next((float(w) for w in words if w.replace(".", "").isdigit()), 6)
        do_buy(WHITELIST[coin], coin, amt)
        return
    if words[0] in ("продай", "продать", "sell") and coin:
        do_sell(WHITELIST[coin], coin)
        return

    # 4. Отчёт
    if words[0] in ("отчет", "отчёт", "баланс", "статус", "/report", "/start"):
        os.system(f'cd "{BASE}" && "{sys.executable}" report_now.py')
        return

    # 4b. Самоанализ сделок (обучение на истории)
    if words[0] in ("анализ", "статистика", "аналитика", "разбор"):
        os.system(f'cd "{BASE}" && "{sys.executable}" self_analysis.py')
        return

    # 5. Свободный текст = ВОПРОС → будим GitHub-мозг, он ответит в бот через пару минут
    with open(INBOX, "a", encoding="utf-8") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + raw + "\n")
    if _trigger_brain(raw):
        send("🤔 Думаю над ответом, собираю данные по рынку… отвечу через пару минут.")
    else:
        send("📝 Принял, учту при следующем анализе. Команды: «докупи SOL 6», «продай UNI», «стоп», «отчет».")


def _trigger_brain(question):
    """Будим воркфлоу answer.yml на GitHub через repository_dispatch."""
    from bybit_client import _ENV
    token = _ENV.get("GITHUB_DISPATCH_TOKEN", "")
    repo = _ENV.get("GITHUB_REPO", "itkarimov/bybit-autopilot")
    if not token:
        return False
    try:
        import urllib.request
        body = json.dumps({"ref": "main", "inputs": {"question": question[:900]}}).encode()
        req = urllib.request.Request(
            f"https://api.github.com/repos/{repo}/actions/workflows/answer.yml/dispatches",
            data=body, method="POST",
            headers={"Authorization": f"token {token}", "Accept": "application/vnd.github+json",
                     "User-Agent": "beget-trader"})
        urllib.request.urlopen(req, timeout=15)
        return True
    except Exception:
        return False


if __name__ == "__main__":
    main()
