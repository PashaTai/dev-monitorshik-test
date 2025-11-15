# Быстрый старт развертывания на VPS

## Подготовлено для вас

✅ **reclassify_all_comments.py** - скрипт для переразметки всех комментариев  
✅ **VPS_DEPLOYMENT_STEPS.md** - детальная пошаговая инструкция  
✅ **GIT_DEPLOYMENT.md** - git-based развертывание  
✅ **.gitignore** - исключает БД, логи и секреты из git  

## Развертывание через Git

Все изменения разворачиваются через `git pull` на VPS сервере. Это самый простой и надежный способ.

**Время выполнения:** ~5-10 минут

---

## Пошаговая инструкция

### 1. Commit и Push изменений (на локальной машине)

```powershell
# Windows PowerShell
cd C:\Users\p.tayanko\Projects\dev-monitorshik-test

# Проверьте что изменилось
git status

# Добавьте все изменения
git add .

# Commit
git commit -m "Добавлена новая Few-shot система тональности"

# Push в репозиторий
git push origin main
```

### 2. Обновите .env файл на VPS

Подключитесь к VPS и обновите конфигурацию:

Убедитесь что в `.env` есть все параметры:

```env
# Yandex API для новой системы
YANDEX_API_KEY=ваш_api_key
YANDEX_FOLDER_ID=ваш_folder_id

# API и Dashboard пароли
API_PASSWORD=надежный_пароль_123
DASHBOARD_PASSWORD=другой_надежный_пароль_456

# URL для API (замените на ваш IP)
API_URL=http://ваш_IP:8000
```

### 3. Получите обновления на VPS

```bash
# Подключитесь к VPS
ssh YOUR_USER@YOUR_IP

# Перейдите в директорию проекта
cd ~/dev-monitorshik-test

# Создайте backup базы данных
cp comments.db comments.db.backup.$(date +%Y%m%d_%H%M%S)

# Получите обновления из Git
git pull origin main

# Обновите зависимости
source venv/bin/activate
pip install -r requirements.txt
```

### 4. Обновите systemd сервисы

```bash
# Скопируйте обновленные сервисы
sudo cp deploy/*.service /etc/systemd/system/

# Отредактируйте пути если нужно (замените YOUR_USER на ваше имя)
sudo nano /etc/systemd/system/unified-monitor.service
sudo nano /etc/systemd/system/sentiment-api.service
sudo nano /etc/systemd/system/sentiment-dashboard.service

# Перезагрузите systemd
sudo systemctl daemon-reload

# Перезапустите сервисы
sudo systemctl restart unified-monitor sentiment-api sentiment-dashboard
```

### 5. Запустите переразметку

```bash
# Используйте screen для надежности
screen -S reclassify

# В screen сессии:
cd ~/dev-monitorshik-test
source venv/bin/activate
python reclassify_all_comments.py

# Отсоединитесь: Ctrl+A, затем D
```

---

## После развертывания

### Проверьте что все работает

1. **Dashboard** - откройте в браузере:
   ```
   http://ваш_IP:8501
   ```
   Введите пароль из `DASHBOARD_PASSWORD`

2. **API** - проверьте в терминале:
   ```bash
   curl http://ваш_IP:8000/api/health
   ```

3. **Статус сервисов:**
   ```bash
   sudo systemctl status unified-monitor sentiment-api sentiment-dashboard
   ```

Все должны быть **active (running)** ✅

---

## Переразметка комментариев

### Запуск в screen (рекомендуется)

```bash
# Создайте screen сессию
screen -S reclassify

# В сессии запустите:
cd ~/dev-monitorshik-test
source venv/bin/activate
python reclassify_all_comments.py

# Отсоединитесь: Ctrl+A, затем D
# Вернитесь: screen -r reclassify
```

### Мониторинг прогресса

В другом терминале:
```bash
tail -f ~/dev-monitorshik-test/logs/reclassify_*.log
```

**Ожидаемое время:** 5-15 минут для 200 комментариев

---

## Что получится в итоге

После завершения у вас будет:

1. ✅ **Unified Monitor** - собирает комментарии из VK и Telegram
2. ✅ **Новая система тональности** - Few-shot Yandex Classifier
3. ✅ **Все комментарии переразмечены** - новой системой
4. ✅ **API сервер** - `http://ваш_IP:8000` для ручной разметки
5. ✅ **Dashboard** - `http://ваш_IP:8501` для просмотра и разметки
6. ✅ **Автозапуск** - все сервисы запустятся после перезагрузки сервера

---

## Полезные команды

### Управление сервисами

```bash
# Статус
sudo systemctl status unified-monitor sentiment-api sentiment-dashboard

# Перезапуск всех
sudo systemctl restart unified-monitor sentiment-api sentiment-dashboard

# Остановка всех
sudo systemctl stop unified-monitor sentiment-api sentiment-dashboard

# Логи в реальном времени
sudo journalctl -u unified-monitor -f
```

### Проверка базы данных

```bash
sqlite3 ~/dev-monitorshik-test/comments.db
```

```sql
-- Статистика по тональности
SELECT sentiment, COUNT(*) as count 
FROM comments 
GROUP BY sentiment;

-- Всего комментариев
SELECT COUNT(*) FROM comments;

-- Выход
.quit
```

---

## Если что-то пошло не так

### 1. Восстановление из backup

```bash
cd ~/dev-monitorshik-test
sudo systemctl stop unified-monitor sentiment-api sentiment-dashboard
mv comments.db comments.db.broken
cp comments.db.backup.YYYYMMDD_HHMMSS comments.db
sudo systemctl start unified-monitor sentiment-api sentiment-dashboard
```

### 2. Проверка логов

```bash
# Логи unified-monitor
sudo journalctl -u unified-monitor -n 100

# Логи API
sudo journalctl -u sentiment-api -n 100

# Логи Dashboard
sudo journalctl -u sentiment-dashboard -n 100

# Файлы логов
tail -100 ~/dev-monitorshik-test/logs/unified-monitor.log
```

### 3. Ручной запуск для диагностики

```bash
cd ~/dev-monitorshik-test
source venv/bin/activate

# Проверка API
python api_server.py

# Проверка Dashboard (в другом терминале)
streamlit run dashboard/streamlit_app.py
```

---

## Контрольный чеклист

Перед тем как считать развертывание завершенным:

- [ ] Backup базы данных создан
- [ ] .env файл обновлен с API ключами и паролями
- [ ] Все файлы загружены на VPS
- [ ] Зависимости обновлены (`pip install -r requirements.txt`)
- [ ] unified-monitor работает (статус active)
- [ ] sentiment-api работает (статус active)
- [ ] sentiment-dashboard работает (статус active)
- [ ] API отвечает на /api/health
- [ ] Dashboard открывается в браузере
- [ ] Переразметка выполнена успешно
- [ ] В БД все комментарии имеют тональность
- [ ] Ручная разметка работает через Dashboard
- [ ] Автозапуск включен для всех сервисов
- [ ] Firewall настроен (порты 8000, 8501)

---

## Дополнительная помощь

- 📖 **Детальная инструкция:** VPS_DEPLOYMENT_STEPS.md
- 🔧 **Автоматический скрипт:** vps_deploy_auto.sh
- 📊 **Общая документация:** DEPLOYMENT.md

Если возникли проблемы - соберите логи и статистику БД (команды в разделе "Если что-то пошло не так").

