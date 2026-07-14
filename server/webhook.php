<?php
// Вебхук Telegram: текст владельца -> очередь (UTF-8) -> reply_handler.py --queue.
// Настройки — в config.php (скопируй из config.example.php).
require __DIR__ . '/config.php';

$hdr = $_SERVER['HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN'] ?? '';
if ($hdr !== SECRET) { http_response_code(403); exit('no'); }

$update = json_decode(file_get_contents('php://input'), true);
$msg = $update['message'] ?? null;
if (!$msg) exit('ok');

$chat_id = $msg['chat']['id'] ?? 0;
$text = trim($msg['text'] ?? '');
if ($chat_id !== OWNER_ID || $text === '') exit('ok');

file_put_contents(DIR . '/bot_queue.txt', $text . "\n", FILE_APPEND | LOCK_EX);
// setsid — отвязываем процесс в новую сессию, иначе PHP-FPM убивает фоновый процесс при
// завершении запроса, и команда (напр. «стоп») не успевает выполниться.
exec('cd ' . DIR . ' && setsid env PYTHONUTF8=1 LC_ALL=C.UTF-8 ' . PY . ' reply_handler.py --queue < /dev/null > /dev/null 2>&1 &');
exit('ok');
