# Руководство по развертыванию на VPS

Пошаговая инструкция по установке и настройке Unified Monitor на VPS сервере.

## Требования

- VPS сервер с Ubuntu 20.04+ / Debian 11+
- Root доступ или sudo права
- Минимум 1GB RAM, 10GB диска
- Открытые порты: 8000 (API), 8501 (Dashboard)
- Python 3.9+

## Шаг 1: Подготовка сервера

### 1.1. Подключитесь к серверу

```bash
ssh your_user@your_server_ip
```

### 1.2. Обновите систему

```bash
sudo apt update && sudo apt upgrade -y
```

### 1.3. Установите необходимые пакеты

```bash
sudo apt install -y python3 python3-pip python3-venv git sqlite3 nginx
```

## Шаг 2: Создание пользователя (опционально)

Рекомендуется запускать приложение от отдельного пользователя:

```bash
sudo useradd -m -s /bin/bash monitor
sudo su - monitor
```

## Шаг 3: Клонирование и установка

### 3.1. Клонируйте репозиторий

```bash
cd ~
git clone <your-repo-url> unified-monitor
cd unified-monitor
```

### 3.2. Создайте виртуальное окружение

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3.3. Установите зависимости

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

## Шаг 4: Конфигурация

### 4.1. Создайте .env файл

```bash
cp env.example .env
nano .env
```

### 4.2. Заполните обязательные параметры

```env
# База данных
DB_PATH=comments.db

# VK (если нужен мониторинг VK)
VK_ACCESS_TOKEN=your_vk_token
VK_GROUP_ID=your_group_id

# Telegram (если нужен мониторинг Telegram)
TG_API_ID=12345678
TG_API_HASH=your_api_hash
TG_STRING_SESSION=your_session_string
CHANNELS=channel1,channel2

# Yandex Cloud для анализа тональности
YANDEX_API_KEY=your_api_key
YANDEX_FOLDER_ID=your_folder_id

# API и Dashboard - ОБЯЗАТЕЛЬНО ИЗМЕНИТЕ ПАРОЛИ!
API_USERNAME=admin
API_PASSWORD=secure_password_123
DASHBOARD_PASSWORD=another_secure_password_456
API_URL=http://localhost:8000
```

**⚠️ ВАЖНО:** Замените пароли на надежные!

### 4.3. Получите Telegram Session (если нужен Telegram мониторинг)

На локальной машине запустите:

```bash
python generate_session.py
```

Скопируйте полученный StringSession в `.env` на сервере.

## Шаг 5: Проверка работоспособности

### 5.1. Инициализация базы данных

```bash
python main.py
```

Нажмите Ctrl+C после успешной инициализации.

### 5.2. Проверка API сервера

```bash
python api_server.py
```

В другом терминале проверьте:

```bash
curl http://localhost:8000/api/health
```

### 5.3. Проверка Dashboard

```bash
streamlit run dashboard/streamlit_app.py
```

Откройте в браузере: `http://your_server_ip:8501`

Если все работает - переходите к настройке systemd.

## Шаг 6: Настройка systemd сервисов

### 6.1. Скопируйте systemd юниты

```bash
sudo cp deploy/*.service /etc/systemd/system/
```

### 6.2. Отредактируйте пути в сервисах

```bash
sudo nano /etc/systemd/system/unified-monitor.service
sudo nano /etc/systemd/system/sentiment-api.service
sudo nano /etc/systemd/system/sentiment-dashboard.service
```

Замените `YOUR_USER` на ваше имя пользователя и исправьте пути:

```ini
User=monitor  # или ваш пользователь
WorkingDirectory=/home/monitor/unified-monitor
Environment="PATH=/home/monitor/unified-monitor/venv/bin"
EnvironmentFile=/home/monitor/unified-monitor/.env
ExecStart=/home/monitor/unified-monitor/venv/bin/python ...
```

### 6.3. Перезагрузите systemd

```bash
sudo systemctl daemon-reload
```

### 6.4. Запустите сервисы

```bash
# Мониторинг комментариев
sudo systemctl enable unified-monitor
sudo systemctl start unified-monitor

# API для разметки
sudo systemctl enable sentiment-api
sudo systemctl start sentiment-api

# Dashboard
sudo systemctl enable sentiment-dashboard
sudo systemctl start sentiment-dashboard
```

### 6.5. Проверьте статус

```bash
sudo systemctl status unified-monitor
sudo systemctl status sentiment-api
sudo systemctl status sentiment-dashboard
```

### 6.6. Просмотр логов

```bash
# Логи через journalctl
sudo journalctl -u unified-monitor -f
sudo journalctl -u sentiment-api -f
sudo journalctl -u sentiment-dashboard -f

# Логи приложения
tail -f ~/unified-monitor/logs/unified-monitor.log
```

## Шаг 7: Настройка Nginx (опционально, но рекомендуется)

### 7.1. Создайте конфигурацию Nginx

```bash
sudo nano /etc/nginx/sites-available/unified-monitor
```

```nginx
# API сервер
server {
    listen 80;
    server_name api.your-domain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

# Dashboard
server {
    listen 80;
    server_name dashboard.your-domain.com;

    location / {
        proxy_pass http://localhost:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
    }
}
```

### 7.2. Активируйте конфигурацию

```bash
sudo ln -s /etc/nginx/sites-available/unified-monitor /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### 7.3. Настройте SSL (рекомендуется)

```bash
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d api.your-domain.com -d dashboard.your-domain.com
```

Обновите `API_URL` в `.env`:

```env
API_URL=https://api.your-domain.com
```

Перезапустите сервисы:

```bash
sudo systemctl restart sentiment-api sentiment-dashboard
```

## Шаг 8: Настройка Firewall

### 8.1. UFW (Ubuntu)

```bash
sudo ufw allow ssh
sudo ufw allow 'Nginx Full'
sudo ufw enable
```

Если не используете Nginx:

```bash
sudo ufw allow 8000/tcp  # API
sudo ufw allow 8501/tcp  # Dashboard
```

## Шаг 9: Автоматическое обновление

### 9.1. Создайте скрипт обновления

```bash
nano ~/unified-monitor/update.sh
```

```bash
#!/bin/bash
cd ~/unified-monitor
git pull
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart unified-monitor sentiment-api sentiment-dashboard
```

```bash
chmod +x ~/unified-monitor/update.sh
```

### 9.2. Обновление проекта

```bash
~/unified-monitor/update.sh
```

## Использование

### Доступ к Dashboard

- Без Nginx: `http://your_server_ip:8501`
- С Nginx: `http://dashboard.your-domain.com`
- С SSL: `https://dashboard.your-domain.com`

Введите пароль из `DASHBOARD_PASSWORD`.

### Управление сервисами

```bash
# Перезапуск
sudo systemctl restart unified-monitor
sudo systemctl restart sentiment-api
sudo systemctl restart sentiment-dashboard

# Остановка
sudo systemctl stop unified-monitor sentiment-api sentiment-dashboard

# Запуск
sudo systemctl start unified-monitor sentiment-api sentiment-dashboard

# Автозапуск при загрузке
sudo systemctl enable unified-monitor sentiment-api sentiment-dashboard
```

## Мониторинг и обслуживание

### Проверка работоспособности

```bash
# Статус сервисов
sudo systemctl status unified-monitor sentiment-api sentiment-dashboard

# Проверка API
curl http://localhost:8000/api/health

# Статистика базы данных
sqlite3 ~/unified-monitor/comments.db "SELECT COUNT(*) FROM comments;"
```

### Резервное копирование

```bash
# Создание бэкапа базы данных
cp ~/unified-monitor/comments.db ~/unified-monitor/comments.db.backup.$(date +%Y%m%d)

# Автоматический бэкап через cron
crontab -e
# Добавьте:
0 2 * * * cp ~/unified-monitor/comments.db ~/unified-monitor/backups/comments.db.$(date +\%Y\%m\%d)
```

### Очистка старых логов

```bash
# Очистка journalctl (старше 7 дней)
sudo journalctl --vacuum-time=7d

# Ротация логов приложения через logrotate
sudo nano /etc/logrotate.d/unified-monitor
```

```
/home/monitor/unified-monitor/logs/*.log {
    daily
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 monitor monitor
}
```

## Устранение проблем

### Сервис не запускается

```bash
# Проверьте логи
sudo journalctl -u unified-monitor -n 50
sudo journalctl -u sentiment-api -n 50

# Проверьте права на файлы
ls -la ~/unified-monitor/.env
ls -la ~/unified-monitor/comments.db

# Проверьте виртуальное окружение
source ~/unified-monitor/venv/bin/activate
python --version
pip list
```

### Dashboard не доступен

```bash
# Проверьте что сервис запущен
sudo systemctl status sentiment-dashboard

# Проверьте порт
sudo netstat -tlnp | grep 8501

# Проверьте Nginx (если используется)
sudo nginx -t
sudo systemctl status nginx
```

### API возвращает ошибки

```bash
# Проверьте доступность API
curl -u admin:your_password http://localhost:8000/api/health

# Проверьте базу данных
sqlite3 ~/unified-monitor/comments.db "SELECT COUNT(*) FROM comments;"

# Проверьте логи
tail -f ~/unified-monitor/logs/unified-monitor-errors.log
```

## Безопасность

### Рекомендации:

1. ✅ Используйте сильные пароли в `.env`
2. ✅ Настройте SSL через Let's Encrypt
3. ✅ Ограничьте доступ через firewall
4. ✅ Регулярно обновляйте систему и зависимости
5. ✅ Делайте резервные копии базы данных
6. ✅ Не публикуйте `.env` файл
7. ✅ Используйте отдельного пользователя для запуска сервисов
8. ✅ Настройте мониторинг и алерты

### Дополнительная защита:

```bash
# Fail2ban для защиты от брутфорса
sudo apt install fail2ban -y

# Автоматические обновления безопасности
sudo apt install unattended-upgrades -y
sudo dpkg-reconfigure --priority=low unattended-upgrades
```

## Автоматизация развертывания

Для упрощения развертывания используйте скрипт:

```bash
bash deploy.sh
```

См. [deploy.sh](deploy/deploy.sh) для деталей.

## Поддержка

При возникновении проблем:

1. Проверьте логи: `sudo journalctl -u unified-monitor -n 100`
2. Проверьте статус: `sudo systemctl status unified-monitor`
3. Проверьте конфигурацию: `cat .env` (без секретов!)
4. Проверьте базу данных: `sqlite3 comments.db "SELECT COUNT(*) FROM comments;"`

## Дополнительные ресурсы

- [README.md](README.md) - Основная документация
- [db.md](db.md) - Схема базы данных
- Yandex Cloud: https://cloud.yandex.ru/docs
- Telegram API: https://my.telegram.org
- VK API: https://dev.vk.com


