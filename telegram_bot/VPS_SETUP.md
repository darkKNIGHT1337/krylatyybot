# Инструкция: Запуск бота на своём VPS

## Что нужно
- VPS сервер (Ubuntu 22.04)
- Рекомендуемые хостинги: Hetzner (от €3.5/мес), DigitalOcean (от $4/мес), TimeWeb (от 150₽/мес)
- Минимальные требования: 1 CPU, 512MB RAM

---

## Шаг 1: Подключись к серверу

```bash
ssh root@IP_ТВОЕГО_СЕРВЕРА
```

## Шаг 2: Установи Python

```bash
apt update && apt upgrade -y
apt install python3 python3-pip python3-venv -y
```

## Шаг 3: Создай папку и загрузи файлы

```bash
mkdir -p /opt/tgbot
cd /opt/tgbot
```

Скопируй файл `bot.py` на сервер (через FileZilla, WinSCP или вставь вручную):

```bash
nano bot.py
# Вставь весь код из bot.py → Ctrl+X → Y → Enter
```

## Шаг 4: Установи зависимости

```bash
pip3 install aiogram==3.13.0
```

## Шаг 5: Убедись что конфиг в bot.py заполнен

В начале `bot.py` должны быть заполнены:
```python
BOT_TOKEN = "8909864249:..."          # ✅ уже заполнен
MAIN_CHANNEL_ID = -1002443521731      # ✅ уже заполнен
VIDEO_SOURCE_CHANNEL = "@krylatyvideoxxfsd"  # ✅ уже заполнен
VIDEO_NOTE_MSG_ID = 5                 # ✅ уже заполнен
# ... остальные тоже заполнены
```

## Шаг 6: Тестовый запуск

```bash
cd /opt/tgbot
python3 bot.py
```

Если видишь `Бот запущен: @ИМЯ_БОТА` — всё работает.
Нажми Ctrl+C чтобы остановить.

---

## Шаг 7: Запуск как постоянный сервис (systemd)

Создай сервис чтобы бот запускался автоматически и перезапускался при падении:

```bash
nano /etc/systemd/system/tgbot.service
```

Вставь это содержимое:
```ini
[Unit]
Description=Telegram Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/tgbot
ExecStart=/usr/bin/python3 /opt/tgbot/bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Сохрани (Ctrl+X → Y → Enter), затем:

```bash
systemctl daemon-reload
systemctl enable tgbot
systemctl start tgbot
```

## Шаг 8: Проверка

```bash
systemctl status tgbot       # Статус сервиса
journalctl -u tgbot -f       # Логи в реальном времени
```

---

## Полезные команды

```bash
systemctl stop tgbot         # Остановить бота
systemctl restart tgbot      # Перезапустить бота
journalctl -u tgbot -n 50    # Последние 50 строк логов
```

---

## Важно

Перед запуском на VPS — **удали старый webhook** чтобы Telegram переключился на polling:

```bash
curl "https://api.telegram.org/botТВОЙ_ТОКЕН/deleteWebhook"
```

Или вставь токен напрямую:
```bash
curl "https://api.telegram.org/bot8909864249:AAGfDR-ookDxTpcCJ0a8Y1_XuFrWxbf8jCA/deleteWebhook"
```

---

## Итог

| | Emergent (webhook) | VPS (polling) |
|---|---|---|
| Стоимость | Тариф Emergent | €3-5/мес |
| Надёжность | Зависит от платформы | 24/7 |
| Сложность | Не надо ничего делать | 15 мин настройки |
| Подходит для | Теста | Продакшна |
