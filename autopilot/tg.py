# -*- coding: utf-8 -*-
"""Отправка сообщений в Telegram-бота отчётов."""
import json
import urllib.parse
import urllib.request

from bybit_client import _ENV


OWNER_ID = int(_ENV.get("TG_CHAT_ID", "0") or 0)  # единственный получатель — владелец из .env


def _autofill_chat_id(token):
    """Если chat_id пуст — восстанавливаем ТОЛЬКО chat_id владельца из getUpdates."""
    import os
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getUpdates", timeout=15) as r:
        upd = json.loads(r.read().decode()).get("result", [])
    for u in reversed(upd):
        chat = (u.get("message") or {}).get("chat") or {}
        if chat.get("id") == OWNER_ID:
            cid = str(chat["id"])
            env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
            with open(env_path, encoding="utf-8") as f:
                content = f.read()
            with open(env_path, "w", encoding="utf-8") as f:
                f.write(content.replace("TG_CHAT_ID=", "TG_CHAT_ID=" + cid, 1))
            _ENV["TG_CHAT_ID"] = cid
            return cid
    return ""


def send(text):
    token = _ENV.get("TG_BOT_TOKEN", "")
    chat_id = _ENV.get("TG_CHAT_ID", "") or (_autofill_chat_id(token) if token else "")
    if str(chat_id) != str(OWNER_ID):
        chat_id = str(OWNER_ID)  # отчёты — только владельцу, что бы ни лежало в .env
    if not token or not chat_id:
        print("TG не настроен (нет токена или chat_id), сообщение:\n" + text)
        return False
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data)
    with urllib.request.urlopen(req, timeout=15) as r:
        ok = json.loads(r.read().decode()).get("ok", False)
    print("TG отправлено" if ok else "TG ошибка")
    return ok
