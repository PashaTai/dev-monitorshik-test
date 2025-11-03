# Пошаговое руководство по развертыванию на VPS

## 📋 Предварительные требования

- VPS с Ubuntu/Debian (или другой Linux)
- Python 3.8+ установлен
- Git установлен
- Доступ по SSH

---

## 🚀 ШАГ 1: Подключение к VPS

```bash
ssh your_user@your_vps_ip
```

---

## 📦 ШАГ 2: Установка зависимостей системы

```bash
# Обновляем систему
sudo apt update && sudo apt upgrade -y

# Устанавливаем Python и необходимые пакеты
sudo apt install -y python3 python3-pip python3-venv git
```

---

## 📁 ШАГ 3: Клонирование/копирование проекта

### Вариант A: Если проект в Git репозитории

```bash
cd ~
git clone https://your-repo-url/dev-monitorshik-test.git
cd dev-monitorshik-test
```

### Вариант B: Если нужно скопировать с локальной машины

На **локальной машине** (Windows):
```bash
# Создаем архив проекта (исключая venv и другие ненужные папки)
# Используйте Git или скопируйте через SCP
```

На **VPS**:
```bash
cd ~
# Загрузите файлы через SCP, rsync или git
```

---

## 🐍 ШАГ 4: Создание виртуального окружения (venv)

```bash
cd ~/dev-monitorshik-test

# Создаем виртуальное окружение
python3 -m venv venv

# Активируем виртуальное окружение
source venv/bin/activate

# Проверяем что активировано (должна быть префикс (venv) в командной строке)
which python
# Должно показать: /home/your_user/dev-monitorshik-test/venv/bin/python
```

**Важно:** После каждого переподключения к VPS нужно активировать venv:
```bash
source ~/dev-monitorshik-test/venv/bin/activate
```

---

## 📚 ШАГ 5: Установка Python зависимостей

```bash
# Убедитесь что venv активирован (должен быть префикс (venv))
# Устанавливаем зависимости
pip install --upgrade pip
pip install -r requirements.txt
```

Проверяем установку:
```bash
pip list
# Должны увидеть: telethon, aiohttp, sqlalchemy, yandex-cloud-ml-sdk и др.
```

---

## ⚙️ ШАГ 6: Настройка конфигурации (.env файл)

```bash
# Копируем пример конфигурации
cp env.example .env

# Редактируем .env файл
nano .env
# или
vim .env
```

### Минимальная конфигурация для запуска:

#### Для VK монитора:
```env
VK_ACCESS_TOKEN=ваш_токен_vk
VK_GROUP_ID=ваша_группа_или_id
```

#### Для Telegram монитора:
```env
TG_API_ID=ваш_api_id
TG_API_HASH=ваш_api_hash
TG_STRING_SESSION=ваша_string_session
CHANNELS=канал1,канал2
```

#### Для анализа тональности (обязательно для уведомлений):
```env
YANDEX_API_KEY=ваш_api_key
YANDEX_FOLDER_ID=ваш_folder_id
```

#### Для уведомлений в Telegram:
```env
BOT_TOKEN=ваш_bot_token
ALERT_CHAT_ID=ваш_chat_id
```

#### Опционально:
```env
DB_PATH=/home/your_user/dev-monitorshik-test/comments.db
LOG_DIR=/home/your_user/dev-monitorshik-test/logs
SENTIMENT_INTERVAL=60
CHECK_INTERVAL=60
```

Сохраняем файл (в nano: `Ctrl+O`, Enter, `Ctrl+X`)

**Важно:** Убедитесь что `.env` файл не публикуется в git (он должен быть в .gitignore)

---

## 🧪 ШАГ 7: Тестовый запуск

```bash
# Убедитесь что venv активирован
source venv/bin/activate

# Создаем директорию для логов (если её нет)
mkdir -p logs

# Запускаем приложение
python main.py
```

### Что должно произойти:

1. Приложение инициализирует БД
2. Запускаются мониторы (VK/Telegram, если настроены)
3. Запускается Sentiment Worker (если настроен YANDEX_API_KEY)
4. В консоли должны быть логи вида:
```
============================================================
Unified Monitor - VK & Telegram Comment Monitor
============================================================
2025-11-03 16:40:00 - main - INFO - Database initialized. Statistics:
2025-11-03 16:40:00 - main - INFO -   Total comments: 0
...
2025-11-03 16:40:05 - main - INFO - All monitors started. Monitoring for new comments...
```

### Если всё работает:
- Нажмите `Ctrl+C` для остановки
- Переходим к следующему шагу

### Если есть ошибки:
- Проверьте логи в консоли
- Убедитесь что все переменные в `.env` заполнены правильно
- Проверьте что venv активирован и зависимости установлены

---

## 🔄 ШАГ 8: Настройка автозапуска через systemd

### 8.1. Создаем systemd service файл

```bash
sudo nano /etc/systemd/system/unified-monitor.service
```

Скопируйте содержимое:

```ini
[Unit]
Description=Unified Monitor - VK & Telegram Comment Monitor with Sentiment Analysis
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/home/your_user/dev-monitorshik-test
Environment="PATH=/home/your_user/dev-monitorshik-test/venv/bin"
ExecStart=/home/your_user/dev-monitorshik-test/venv/bin/python /home/your_user/dev-monitorshik-test/main.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

**Важно:** Замените `your_user` на ваше имя пользователя!

Сохраните файл (`Ctrl+O`, Enter, `Ctrl+X`)

### 8.2. Обновляем systemd и запускаем сервис

```bash
# Перезагружаем конфигурацию systemd
sudo systemctl daemon-reload

# Включаем автозапуск при загрузке системы
sudo systemctl enable unified-monitor.service

# Запускаем сервис
sudo systemctl start unified-monitor.service

# Проверяем статус
sudo systemctl status unified-monitor.service
```

### 8.3. Полезные команды для управления сервисом

```bash
# Проверить статус
sudo systemctl status unified-monitor.service

# Остановить
sudo systemctl stop unified-monitor.service

# Запустить
sudo systemctl start unified-monitor.service

# Перезапустить
sudo systemctl restart unified-monitor.service

# Просмотр логов
sudo journalctl -u unified-monitor.service -f

# Последние 100 строк логов
sudo journalctl -u unified-monitor.service -n 100
```

---

## 📊 ШАГ 9: Проверка работы

### 9.1. Проверяем что сервис работает

```bash
sudo systemctl status unified-monitor.service
```

Должно быть: `Active: active (running)`

### 9.2. Проверяем логи

```bash
sudo journalctl -u unified-monitor.service -f
```

Или логи в файле:
```bash
tail -f ~/dev-monitorshik-test/logs/unified-monitor.log
```

### 9.3. Проверяем базу данных

```bash
cd ~/dev-monitorshik-test
source venv/bin/activate
sqlite3 comments.db "SELECT COUNT(*) as total FROM comments;"
sqlite3 comments.db "SELECT source, COUNT(*) FROM comments GROUP BY source;"
sqlite3 comments.db "SELECT sentiment, COUNT(*) FROM comments WHERE sentiment IS NOT NULL GROUP BY sentiment;"
```

### 9.4. Проверяем что комментарии обрабатываются

Дождитесь новых комментариев (или создайте тестовый) и проверьте:
- Комментарий появился в БД
- Через 60 секунд sentiment проанализирован
- Уведомление пришло в Telegram (если настроено)

---

## 🔧 ШАГ 10: Настройка ротации логов (опционально)

Если логи растут слишком быстро:

```bash
sudo nano /etc/logrotate.d/unified-monitor
```

Содержимое:
```
/home/your_user/dev-monitorshik-test/logs/*.log {
    daily
    rotate 7
    compress
    delaycompress
    notifempty
    missingok
}
```

---

## 🛡️ ШАГ 11: Безопасность

### 11.1. Права доступа к .env файлу

```bash
chmod 600 ~/dev-monitorshik-test/.env
```

### 11.2. Права доступа к БД (если нужно)

```bash
chmod 644 ~/dev-monitorshik-test/comments.db
```

### 11.3. Firewall (если нужно)

```bash
# Обычно не нужно, т.к. приложение только делает исходящие запросы
# Но если нужен доступ к какому-то API:
sudo ufw allow from your_ip
```

---

## 📝 ШАГ 12: Обновление проекта

Если нужно обновить код:

```bash
cd ~/dev-monitorshik-test

# Если используете git:
git pull

# Если обновлены зависимости:
source venv/bin/activate
pip install -r requirements.txt

# Перезапускаем сервис
sudo systemctl restart unified-monitor.service
```

---

## 🐛 Решение проблем

### Проблема: Сервис не запускается

```bash
# Проверяем логи ошибок
sudo journalctl -u unified-monitor.service -n 50

# Проверяем что venv активирован в пути
ls -la /home/your_user/dev-monitorshik-test/venv/bin/python

# Проверяем права на файлы
ls -la ~/dev-monitorshik-test/main.py
```

### Проблема: "Module not found"

```bash
# Убедитесь что venv активирован в systemd service
# Или переустановите зависимости
source venv/bin/activate
pip install -r requirements.txt --force-reinstall
```

### Проблема: Комментарии не сохраняются в БД

```bash
# Проверяем права на файл БД
ls -la ~/dev-monitorshik-test/comments.db

# Проверяем что БД создается
sqlite3 ~/dev-monitorshik-test/comments.db ".tables"
```

### Проблема: Sentiment не работает

```bash
# Проверяем что YANDEX_API_KEY и YANDEX_FOLDER_ID установлены
cat ~/dev-monitorshik-test/.env | grep YANDEX

# Тестируем вручную
source venv/bin/activate
python -c "from sentiment.yandex_analyzer import YandexSentimentAnalyzer; print('OK')"
```

---

## ✅ Чеклист готовности

- [ ] Python 3.8+ установлен
- [ ] Git установлен
- [ ] Проект скопирован на VPS
- [ ] Виртуальное окружение создано и активировано
- [ ] Все зависимости установлены (`pip install -r requirements.txt`)
- [ ] `.env` файл создан и заполнен
- [ ] Тестовый запуск прошел успешно
- [ ] systemd service создан и запущен
- [ ] Сервис автоматически стартует при загрузке (`systemctl enable`)
- [ ] Логи проверены, нет ошибок
- [ ] Тестовый комментарий обработан успешно

---

## 🎉 Готово!

После выполнения всех шагов ваш проект должен работать на VPS:

- ✅ Автоматически стартует при перезагрузке сервера
- ✅ Перезапускается при падении (Restart=always)
- ✅ Логи пишутся в systemd journal и в файлы
- ✅ Все мониторы работают автоматически

Для мониторинга используйте:
```bash
sudo journalctl -u unified-monitor.service -f
```

Удачи! 🚀

