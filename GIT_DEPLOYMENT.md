# Git-based развертывание на VPS

Все изменения разворачиваются через `git pull` на VPS сервере.

## Быстрая инструкция

### На локальной машине (Windows)

```powershell
cd C:\Users\p.tayanko\Projects\dev-monitorshik-test

# Проверьте изменения
git status

# Добавьте файлы
git add .

# Commit
git commit -m "Описание изменений"

# Push
git push origin main
```

### На VPS сервере

```bash
# Подключитесь к VPS
ssh YOUR_USER@YOUR_IP

# Перейдите в проект
cd ~/dev-monitorshik-test

# Получите изменения
git pull origin main

# Обновите зависимости (если нужно)
source venv/bin/activate
pip install -r requirements.txt

# Перезапустите сервисы
sudo systemctl restart unified-monitor sentiment-api sentiment-dashboard
```

## Первое развертывание

Если проект еще не клонирован на VPS:

```bash
# На VPS
cd ~
git clone https://github.com/ваш-username/dev-monitorshik-test.git
cd dev-monitorshik-test

# Создайте виртуальное окружение
python3 -m venv venv
source venv/bin/activate

# Установите зависимости
pip install -r requirements.txt

# Создайте .env из примера
cp env.example .env
nano .env  # Отредактируйте

# Настройте systemd сервисы
sudo cp deploy/*.service /etc/systemd/system/
# Отредактируйте пути в сервисах
sudo nano /etc/systemd/system/unified-monitor.service
sudo nano /etc/systemd/system/sentiment-api.service
sudo nano /etc/systemd/system/sentiment-dashboard.service

# Запустите
sudo systemctl daemon-reload
sudo systemctl enable unified-monitor sentiment-api sentiment-dashboard
sudo systemctl start unified-monitor sentiment-api sentiment-dashboard
```

## .gitignore

Файл `.gitignore` уже настроен и исключает:
- `comments.db` - база данных
- `.env` - секреты и конфигурация
- `logs/` - логи
- `venv/` - виртуальное окружение
- `__pycache__/` - Python cache

Эти файлы НЕ попадут в git, что правильно.

## Проверка перед commit

```bash
# Проверьте что именно попадет в commit
git status

# Посмотрите изменения
git diff

# Убедитесь что НЕ добавляются:
# - comments.db
# - .env
# - логи
```

## Полезные команды

```bash
# Отменить последний commit (если еще не push)
git reset --soft HEAD~1

# Посмотреть историю
git log --oneline

# Посмотреть что изменилось в файле
git diff filename

# Обновить только конкретные файлы на VPS
git pull origin main -- path/to/file.py
```

## Структура коммитов

Примеры хороших commit сообщений:

```bash
git commit -m "Добавлена Few-shot система анализа тональности"
git commit -m "Исправлен баг в API для ручной разметки"
git commit -m "Обновлен Dashboard: добавлена секция переразметки"
git commit -m "Обновлены зависимости: streamlit 1.38.0"
```

## Workflow для изменений

1. **Локально:** Вносите изменения в код
2. **Локально:** Тестируйте изменения
3. **Локально:** `git add .` → `git commit -m "..."` → `git push`
4. **На VPS:** `git pull` → `pip install -r requirements.txt` → `systemctl restart ...`
5. **На VPS:** Проверьте что все работает

## Troubleshooting

### Конфликты при git pull

```bash
# Если есть локальные изменения на VPS
git stash  # Сохранить изменения
git pull   # Получить обновления
git stash pop  # Вернуть изменения
```

### Случайно добавили .env в git

```bash
# Удалите из git (но оставьте локально)
git rm --cached .env
git commit -m "Удален .env из git"
git push
```

### Вернуть к предыдущей версии

```bash
# Посмотрите историю
git log --oneline

# Вернитесь к конкретному commit
git checkout <commit-hash>

# Или откатите последний commit
git revert HEAD
```

