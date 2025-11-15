# 🚀 Git-based развертывание готово!

Все переделано под git workflow. Автоматический скрипт развертывания удален.

## ✅ Что было сделано

### 1. Создан .gitignore

Исключает из git:
- `comments.db` - база данных
- `.env` - секреты
- `logs/` - логи
- `venv/` - виртуальное окружение
- `__pycache__/` - Python cache

### 2. Удален vps_deploy_auto.sh

Больше нет автоматического скрипта. Все через git.

### 3. Обновлена документация

Все инструкции теперь используют git workflow:
- **GIT_DEPLOYMENT.md** - детальный Git workflow ⭐
- **START_HERE.md** - обновлен под git
- **QUICK_START_VPS.md** - обновлен под git
- **DEPLOYMENT_SUMMARY.md** - итоговая сводка

---

## 🎯 Как развернуть на VPS

### На Windows (локально)

```powershell
cd C:\Users\p.tayanko\Projects\dev-monitorshik-test

# Добавьте файлы
git add .

# Commit
git commit -m "Добавлена Few-shot система тональности"

# Push
git push origin main
```

### На VPS

```bash
# Подключитесь
ssh YOUR_USER@YOUR_IP

# Перейдите в проект
cd ~/dev-monitorshik-test

# Backup БД
cp comments.db comments.db.backup.$(date +%Y%m%d_%H%M%S)

# Получите обновления
git pull origin main

# Обновите зависимости
source venv/bin/activate
pip install -r requirements.txt

# Перезапустите сервисы
sudo systemctl restart unified-monitor sentiment-api sentiment-dashboard

# Проверьте статус
sudo systemctl status unified-monitor sentiment-api sentiment-dashboard
```

### Переразметка комментариев

```bash
# Запустите в screen
screen -S reclassify
cd ~/dev-monitorshik-test
source venv/bin/activate
python reclassify_all_comments.py

# Отсоединитесь: Ctrl+A, затем D
# Вернитесь: screen -r reclassify
```

---

## 📚 Документация

| Файл | Описание |
|------|----------|
| **GIT_DEPLOYMENT.md** | ⭐ Детальный Git workflow |
| **START_HERE.md** | Главная точка входа |
| **QUICK_START_VPS.md** | Быстрый старт |
| **DEPLOYMENT_SUMMARY.md** | Итоговая сводка |
| **VPS_DEPLOYMENT_STEPS.md** | Детальные команды |

---

## 🔍 Что в .gitignore

База данных, логи и секреты НЕ попадут в git:

```
# База данных
comments.db
comments.db.*
*.db

# Конфигурация
.env

# Логи
logs/
*.log

# Python
__pycache__/
venv/

# Backup
*.backup.*
backups/
```

---

## ✨ Готово!

Теперь можно коммитить и пушить изменения:

```bash
git add .
git commit -m "Первый commit с новой системой"
git push origin main
```

На VPS просто делайте `git pull` для получения обновлений! 🚀

