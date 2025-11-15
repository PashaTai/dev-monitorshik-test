# Пошаговые инструкции для развертывания на VPS

Этот документ содержит точные команды для выполнения каждого шага развертывания на вашем VPS сервере.

## Предварительная подготовка

Убедитесь что у вас есть:
- SSH доступ к VPS
- Имя пользователя на VPS
- IP адрес VPS
- Yandex API ключи (YANDEX_API_KEY, YANDEX_FOLDER_ID)

---

## ШАГ 1: Подключение к VPS

```bash
# Замените YOUR_USER и YOUR_IP на ваши данные
ssh YOUR_USER@YOUR_IP

# Перейдите в директорию проекта
cd ~/dev-monitorshik-test
```

---

## ШАГ 2: Создание backup базы данных

**ВАЖНО: Сделайте backup перед любыми изменениями!**

```bash
# Создайте backup с временной меткой
cp comments.db comments.db.backup.$(date +%Y%m%d_%H%M%S)

# Проверьте что backup создан
ls -lh comments.db*

# Вы должны увидеть два файла:
# comments.db (оригинал)
# comments.db.backup.YYYYMMDD_HHMMSS (backup)
```

---

## ШАГ 3: Обновление кода

### Вариант A: Через Git (если проект в репозитории)

```bash
# Сохраните локальные изменения
git stash

# Обновите код
git pull origin main  # или master, в зависимости от вашей ветки

# Верните локальные изменения если нужно
git stash pop
```

### Вариант B: Через SCP (загрузка файлов с локальной машины)

**На локальной машине (Windows PowerShell):**

```powershell
# Перейдите в директорию проекта
cd C:\Users\p.tayanko\Projects\dev-monitorshik-test

# Загрузите необходимые файлы на VPS
scp reclassify_all_comments.py YOUR_USER@YOUR_IP:~/dev-monitorshik-test/
scp sentiment/yandex_analyzer.py YOUR_USER@YOUR_IP:~/dev-monitorshik-test/sentiment/
scp api_server.py YOUR_USER@YOUR_IP:~/dev-monitorshik-test/
scp dashboard/streamlit_app.py YOUR_USER@YOUR_IP:~/dev-monitorshik-test/dashboard/
scp deploy/sentiment-api.service YOUR_USER@YOUR_IP:~/dev-monitorshik-test/deploy/
scp deploy/sentiment-dashboard.service YOUR_USER@YOUR_IP:~/dev-monitorshik-test/deploy/
scp deploy/unified-monitor.service YOUR_USER@YOUR_IP:~/dev-monitorshik-test/deploy/
```

---

## ШАГ 4: Обновление зависимостей

```bash
# Активируйте виртуальное окружение
source venv/bin/activate

# Обновите pip
pip install --upgrade pip

# Установите/обновите зависимости
pip install -r requirements.txt

# Проверьте что все установлено
pip list | grep -E "(fastapi|uvicorn|streamlit|telethon|aiohttp)"
```

---

## ШАГ 5: Обновление .env файла

```bash
# Откройте .env для редактирования
nano .env
```

**Добавьте/проверьте следующие параметры:**

```env
# Yandex API для новой системы тональности
YANDEX_API_KEY=ваш_yandex_api_key
YANDEX_FOLDER_ID=ваш_folder_id

# API сервер для ручной разметки
API_HOST=0.0.0.0
API_PORT=8000
API_URL=http://ваш_IP:8000
API_USERNAME=admin
API_PASSWORD=ваш_надежный_пароль_123

# Dashboard
DASHBOARD_PASSWORD=другой_надежный_пароль_456
DASHBOARD_PORT=8501
```

**Сохраните файл:**
- Нажмите `Ctrl + O` (сохранить)
- Нажмите `Enter` (подтвердить)
- Нажмите `Ctrl + X` (выйти)

---

## ШАГ 6: Остановка старого монитора

```bash
# Остановите монитор
sudo systemctl stop unified-monitor

# Проверьте что остановлен
sudo systemctl status unified-monitor
```

---

## ШАГ 7: Обновление systemd сервиса unified-monitor

```bash
# Скопируйте обновленный сервис
sudo cp deploy/unified-monitor.service /etc/systemd/system/

# Отредактируйте пути (если нужно)
sudo nano /etc/systemd/system/unified-monitor.service
```

**Проверьте что указаны правильные пути:**
- `User=ваш_пользователь`
- `WorkingDirectory=/home/ваш_пользователь/dev-monitorshik-test`
- `Environment="PATH=/home/ваш_пользователь/dev-monitorshik-test/venv/bin"`
- `EnvironmentFile=/home/ваш_пользователь/dev-monitorshik-test/.env`
- `ExecStart=/home/ваш_пользователь/dev-monitorshik-test/venv/bin/python /home/ваш_пользователь/dev-monitorshik-test/main.py`

**Сохраните и перезагрузите systemd:**

```bash
sudo systemctl daemon-reload

# Запустите монитор с новым кодом
sudo systemctl start unified-monitor

# Проверьте что работает
sudo systemctl status unified-monitor

# Посмотрите логи
sudo journalctl -u unified-monitor -n 50 -f
```

**Нажмите `Ctrl + C` для выхода из просмотра логов**

---

## ШАГ 8: Настройка API сервера

```bash
# Скопируйте systemd сервис
sudo cp deploy/sentiment-api.service /etc/systemd/system/

# Отредактируйте пути
sudo nano /etc/systemd/system/sentiment-api.service
```

**Проверьте и исправьте пути:**
- Замените `YOUR_USER` на ваше имя пользователя
- Замените `/home/YOUR_USER/unified-monitor` на `/home/ваш_пользователь/dev-monitorshik-test`

**Запустите API сервер:**

```bash
# Перезагрузите systemd
sudo systemctl daemon-reload

# Включите автозапуск
sudo systemctl enable sentiment-api

# Запустите сервис
sudo systemctl start sentiment-api

# Проверьте статус
sudo systemctl status sentiment-api

# Проверьте что API отвечает
curl http://localhost:8000/api/health
```

**Ожидаемый результат:**
```json
{
  "status": "healthy",
  "database": "comments.db",
  "total_comments": 200,
  "unprocessed_comments": 0
}
```

---

## ШАГ 9: Настройка Dashboard

```bash
# Скопируйте systemd сервис
sudo cp deploy/sentiment-dashboard.service /etc/systemd/system/

# Отредактируйте пути
sudo nano /etc/systemd/system/sentiment-dashboard.service
```

**Проверьте и исправьте пути (аналогично API сервису)**

**Запустите Dashboard:**

```bash
# Перезагрузите systemd
sudo systemctl daemon-reload

# Включите автозапуск
sudo systemctl enable sentiment-dashboard

# Запустите сервис
sudo systemctl start sentiment-dashboard

# Проверьте статус
sudo systemctl status sentiment-dashboard

# Проверьте что Dashboard работает
curl http://localhost:8501
```

---

## ШАГ 10: Настройка Firewall (если используется UFW)

```bash
# Проверьте статус firewall
sudo ufw status

# Если firewall активен, добавьте правила
sudo ufw allow 8000/tcp comment 'Sentiment API'
sudo ufw allow 8501/tcp comment 'Sentiment Dashboard'

# Проверьте правила
sudo ufw status numbered
```

---

## ШАГ 11: Переразметка всех комментариев

**ВАЖНО: Запустите это в screen или tmux, чтобы процесс не прервался при отключении SSH**

### Вариант A: Использование screen (рекомендуется)

```bash
# Установите screen если его нет
sudo apt install screen -y

# Создайте новую screen сессию
screen -S reclassify

# В screen сессии:
cd ~/dev-monitorshik-test
source venv/bin/activate
python reclassify_all_comments.py
```

**Управление screen:**
- `Ctrl + A, затем D` - отсоединиться от сессии (процесс продолжит работать)
- `screen -r reclassify` - вернуться к сессии
- `screen -ls` - список сессий

### Вариант B: Прямой запуск (если быстрое подключение)

```bash
cd ~/dev-monitorshik-test
source venv/bin/activate
python reclassify_all_comments.py
```

**В другом терминале можете отслеживать прогресс:**

```bash
# Подключитесь к VPS во втором терминале
ssh YOUR_USER@YOUR_IP

# Следите за логами
tail -f ~/dev-monitorshik-test/logs/reclassify_*.log
```

**Ожидаемое время выполнения:** 5-15 минут для 200 комментариев

---

## ШАГ 12: Проверка работы системы

### 12.1 Проверка Dashboard

**Откройте в браузере:**
```
http://ваш_IP:8501
```

**Проверьте:**
- ✅ Страница загружается
- ✅ Запрашивает пароль (из DASHBOARD_PASSWORD)
- ✅ После входа показывает статистику
- ✅ Все комментарии имеют тональность (нет "Неопределено" или их мало)
- ✅ Секция "Ручная разметка тональности" работает

### 12.2 Проверка API

```bash
# Проверьте health endpoint
curl http://localhost:8000/api/health

# Проверьте статистику
curl -u admin:ваш_пароль http://localhost:8000/api/stats

# Проверьте неопределенные комментарии
curl -u admin:ваш_пароль http://localhost:8000/api/comments/undefined
```

### 12.3 Проверка мониторов

```bash
# Проверьте статус всех сервисов
sudo systemctl status unified-monitor sentiment-api sentiment-dashboard

# Все должны быть active (running)

# Посмотрите недавние логи unified-monitor
sudo journalctl -u unified-monitor -n 100

# Проверьте что новые комментарии анализируются
sudo journalctl -u unified-monitor -n 50 | grep -i "sentiment"
```

### 12.4 Проверка базы данных

```bash
# Запустите SQLite
sqlite3 ~/dev-monitorshik-test/comments.db

# В SQLite выполните запросы:
```

```sql
-- Всего комментариев
SELECT COUNT(*) as total FROM comments;

-- Статистика по тональности
SELECT 
    sentiment, 
    COUNT(*) as count 
FROM comments 
GROUP BY sentiment;

-- Комментарии без тональности
SELECT COUNT(*) FROM comments WHERE sentiment IS NULL;

-- Выход
.quit
```

---

## ШАГ 13: Проверка автозапуска

```bash
# Проверьте что все сервисы включены для автозапуска
systemctl is-enabled unified-monitor
systemctl is-enabled sentiment-api
systemctl is-enabled sentiment-dashboard

# Все должны вернуть "enabled"
```

---

## Полезные команды для управления

### Просмотр логов

```bash
# Логи unified-monitor (мониторы + анализ тональности)
sudo journalctl -u unified-monitor -f

# Логи API
sudo journalctl -u sentiment-api -f

# Логи Dashboard
sudo journalctl -u sentiment-dashboard -f

# Логи переразметки
tail -f ~/dev-monitorshik-test/logs/reclassify_*.log

# Логи мониторов (файлы)
tail -f ~/dev-monitorshik-test/logs/unified-monitor.log
tail -f ~/dev-monitorshik-test/logs/unified-monitor-errors.log
```

### Перезапуск сервисов

```bash
# Перезапуск всех сервисов
sudo systemctl restart unified-monitor sentiment-api sentiment-dashboard

# Перезапуск отдельных сервисов
sudo systemctl restart unified-monitor
sudo systemctl restart sentiment-api
sudo systemctl restart sentiment-dashboard
```

### Остановка сервисов

```bash
# Остановка всех сервисов
sudo systemctl stop unified-monitor sentiment-api sentiment-dashboard
```

### Статус сервисов

```bash
# Краткий статус всех сервисов
systemctl status unified-monitor sentiment-api sentiment-dashboard --no-pager

# Детальный статус
systemctl status unified-monitor
systemctl status sentiment-api
systemctl status sentiment-dashboard
```

---

## Что делать если что-то пошло не так

### API не запускается

```bash
# Проверьте логи
sudo journalctl -u sentiment-api -n 100

# Проверьте что порт 8000 свободен
sudo netstat -tlnp | grep 8000

# Проверьте права на файлы
ls -la ~/dev-monitorshik-test/.env
ls -la ~/dev-monitorshik-test/comments.db

# Попробуйте запустить вручную
cd ~/dev-monitorshik-test
source venv/bin/activate
python api_server.py
```

### Dashboard не запускается

```bash
# Проверьте логи
sudo journalctl -u sentiment-dashboard -n 100

# Проверьте что порт 8501 свободен
sudo netstat -tlnp | grep 8501

# Попробуйте запустить вручную
cd ~/dev-monitorshik-test
source venv/bin/activate
streamlit run dashboard/streamlit_app.py
```

### Мониторы не собирают комментарии

```bash
# Проверьте логи
sudo journalctl -u unified-monitor -n 200

# Проверьте .env файл
cat ~/dev-monitorshik-test/.env | grep -v PASSWORD

# Проверьте что виртуальное окружение активно
which python
# Должно показать: /home/ваш_пользователь/dev-monitorshik-test/venv/bin/python
```

### Переразметка не работает

```bash
# Проверьте что YANDEX_API_KEY и YANDEX_FOLDER_ID установлены
source venv/bin/activate
python -c "from config.settings import Settings; Settings.load(); print(f'API Key: {Settings.YANDEX_API_KEY[:10]}...'); print(f'Folder ID: {Settings.YANDEX_FOLDER_ID}')"

# Посмотрите последние логи переразметки
ls -lt ~/dev-monitorshik-test/logs/reclassify_*.log | head -1
tail -100 $(ls -t ~/dev-monitorshik-test/logs/reclassify_*.log | head -1)
```

---

## Восстановление из backup

Если что-то пошло не так:

```bash
# Остановите все сервисы
sudo systemctl stop unified-monitor sentiment-api sentiment-dashboard

# Восстановите базу данных из backup
cd ~/dev-monitorshik-test
mv comments.db comments.db.broken
cp comments.db.backup.YYYYMMDD_HHMMSS comments.db

# Запустите сервисы
sudo systemctl start unified-monitor sentiment-api sentiment-dashboard
```

---

## Финальная проверка

После выполнения всех шагов проверьте:

- ✅ Unified Monitor работает (собирает комментарии)
- ✅ Новые комментарии анализируются Few-shot системой
- ✅ API сервер отвечает на http://ваш_IP:8000/api/health
- ✅ Dashboard доступен на http://ваш_IP:8501
- ✅ Все комментарии в БД переразмечены новой системой
- ✅ Ручная разметка работает через Dashboard
- ✅ Все сервисы настроены для автозапуска

---

## Контакты и поддержка

Если возникли проблемы, соберите следующую информацию:

```bash
# Версия Python
python --version

# Статус сервисов
systemctl status unified-monitor sentiment-api sentiment-dashboard --no-pager

# Последние 50 строк логов
sudo journalctl -u unified-monitor -n 50 > ~/logs_unified.txt
sudo journalctl -u sentiment-api -n 50 > ~/logs_api.txt
sudo journalctl -u sentiment-dashboard -n 50 > ~/logs_dashboard.txt

# Статистика БД
sqlite3 ~/dev-monitorshik-test/comments.db "SELECT sentiment, COUNT(*) FROM comments GROUP BY sentiment;" > ~/db_stats.txt
```

**Отправьте файлы:**
- `~/logs_unified.txt`
- `~/logs_api.txt`
- `~/logs_dashboard.txt`
- `~/db_stats.txt`
- Последний `~/dev-monitorshik-test/logs/reclassify_*.log`

