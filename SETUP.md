# Установка — пошагово

> Совет: проще всего открыть этот репозиторий в **Claude Code** и попросить провести по шагам —
> ассистент выполнит команды за тебя. Ниже — ручная инструкция, если хочешь сам.

---

## Шаг 1. Telegram-бот

1. Напиши [@BotFather](https://t.me/BotFather) → `/newbot` → задай имя → получи **токен**.
2. У @BotFather: `/setjoingroups` → выбери бота → **Disable** (чтобы не добавляли в группы).
3. Напиши своему боту любое сообщение, затем узнай свой **chat_id** через [@userinfobot](https://t.me/userinfobot).

## Шаг 2. Bybit API-ключ

1. Bybit → профиль → **API** → Create New Key → **System-generated**.
2. Права: **Read-Write**, **Unified Trading → Trade**, **SPOT → Trade**.
3. ❌ **Withdrawal НЕ включать** — это защита: даже при утечке ключа деньги не выведут.
4. IP: без ограничений (ключ живёт 90 дней) — или впиши IP сервера.
5. Сохрани **API Key** и **Secret**.

## Шаг 3. Сервер (Python + SSH + cron)

1. Залей папку `autopilot/` на сервер, например в `~/trader/`.
2. Создай там `.env` из `autopilot/.env.example`, впиши свои ключи Bybit + токен/chat_id Telegram.
3. Проверь: `python3 ~/trader/report_now.py` — должен прийти отчёт в бот.
4. Настрой **cron** (каждые 30 мин) на механику:
   ```
   2,32 * * * * cd ~/trader && python3 trader_cron.py >> cron.log 2>&1
   ```
5. Залей `server/webhook.php`, скопируй `server/config.example.php` → `config.php`, заполни
   (chat_id, случайный SECRET, путь к python3, путь к папке). Открой доступ к `webhook.php`.

## Шаг 4. GitHub (мозг + чат-вопросы)

1. Создай репозиторий (можно приватный), залей туда содержимое этой папки.
2. Создай **отдельный SSH-ключ** для GitHub↔сервер: `ssh-keygen -t ed25519 -f deploy_key`,
   публичную часть добавь в `~/.ssh/authorized_keys` на сервере.
3. Settings → Secrets and variables → **Actions** → добавь секреты:

   | Секрет | Значение |
   |--------|----------|
   | `BYBIT_API_KEY` / `BYBIT_API_SECRET` | ключи Bybit |
   | `TG_BOT_TOKEN` / `TG_CHAT_ID` | бот и твой chat_id |
   | `SERVER_SSH` | `user@host` для SSH |
   | `SERVER_HOST` | `host` (без user) |
   | `SERVER_DIR` | путь к папке бота, напр. `/home/user/trader` |
   | `SERVER_PY` | путь к python3 на сервере |
   | `BEGET_SSH_KEY` | приватная часть deploy_key (весь текст) |
   | `CLAUDE_CODE_OAUTH_TOKEN` | выполни `claude setup-token` локально, вставь результат |

4. Мозг запустится сам по расписанию (`autopilot.yml`, каждый час). Проверь вкладку **Actions**.

## Шаг 5. Живой чат-вопросы (опционально)

1. Создай **fine-grained PAT**: github.com/settings/personal-access-tokens/new →
   только этот репо → **Actions: Read and write**.
2. Впиши его на сервере в `.env` как `GITHUB_DISPATCH_TOKEN` и `GITHUB_REPO=логин/репо`.
3. Привяжи вебхук Telegram:
   ```
   curl "https://api.telegram.org/bot<ТОКЕН>/setWebhook" \
     -d "url=https://твой-сервер/путь/webhook.php" \
     -d "secret_token=<SECRET из config.php>"
   ```

## Шаг 6. Правила торговли

Открой `autopilot/CLAUDE.md`-аналог — правила зашиты в промптах `AUTOPILOT_CI.md` и коде:
белый список монет, размер позиций, пороги. Подстрой под себя (свои монеты, суммы, риск).

## Проверка

- Напиши боту `отчет` → придёт состояние.
- Напиши боту вопрос («что по рынку?») → через пару минут придёт разбор.
- Дождись тика cron → в `cron.log` появятся записи.

Готово. Комп можно выключать — всё работает на сервере и GitHub.
