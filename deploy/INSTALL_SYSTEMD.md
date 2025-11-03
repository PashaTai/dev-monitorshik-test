# Установка systemd service для Unified Monitor

## Инструкция по установке

1. **Отредактируйте service файл:**

   Откройте `deploy/unified-monitor.service` и измените следующие строки:
   
   - `User=YOUR_USER` - замените на вашего пользователя (например, `ubuntu`, `admin`)
   - `WorkingDirectory=/home/YOUR_USER/dev-monitorshik-test` - путь к проекту
   - `Environment="PATH=..."` - путь к venv/bin (важно для использования venv!)
   - `EnvironmentFile=/home/YOUR_USER/dev-monitorshik-test/.env` - путь к файлу `.env`
   - `ExecStart=/home/YOUR_USER/dev-monitorshik-test/venv/bin/python ...` - используем Python из venv
   
   **ВАЖНО:** Используем Python из venv, а не системный!
   
   Пример:
   ```ini
   User=ubuntu
   WorkingDirectory=/home/ubuntu/dev-monitorshik-test
   Environment="PATH=/home/ubuntu/dev-monitorshik-test/venv/bin"
   EnvironmentFile=/home/ubuntu/dev-monitorshik-test/.env
   ExecStart=/home/ubuntu/dev-monitorshik-test/venv/bin/python /home/ubuntu/dev-monitorshik-test/main.py
   ```

2. **Скопируйте service файл в systemd:**

   ```bash
   sudo cp deploy/unified-monitor.service /etc/systemd/system/
   ```

3. **Перезагрузите systemd daemon:**

   ```bash
   sudo systemctl daemon-reload
   ```

4. **Включите автозапуск:**

   ```bash
   sudo systemctl enable unified-monitor.service
   ```

5. **Запустите сервис:**

   ```bash
   sudo systemctl start unified-monitor.service
   ```

6. **Проверьте статус:**

   ```bash
   sudo systemctl status unified-monitor.service
   ```

## Управление сервисом

- **Остановка:**
  ```bash
  sudo systemctl stop unified-monitor.service
  ```

- **Перезапуск:**
  ```bash
  sudo systemctl restart unified-monitor.service
  ```

- **Просмотр логов:**
  ```bash
  sudo journalctl -u unified-monitor.service -f
  ```

- **Просмотр последних логов:**
  ```bash
  sudo journalctl -u unified-monitor.service -n 100
   ```

- **Отключить автозапуск:**
  ```bash
  sudo systemctl disable unified-monitor.service
  ```

## Настройка Python интерпретатора

Если Python находится в другом месте или используется виртуальное окружение:

1. **Найдите Python:**
   ```bash
   which python3
   # или для venv:
   which /path/to/venv/bin/python
   ```

2. **Используйте полный путь в ExecStart:**
   ```ini
   ExecStart=/path/to/venv/bin/python /path/to/dev-monitorshik-test/main.py
   ```

## Переменные окружения

Сервис использует файл `.env` для переменных окружения. Убедитесь, что:

1. Файл `.env` существует и содержит все необходимые переменные
2. Путь в `EnvironmentFile` указан правильно
3. Файл `.env` доступен для чтения пользователю сервиса

Альтернативно, можно указать переменные напрямую в service файле:
```ini
Environment="TG_API_ID=12345678"
Environment="TG_API_HASH=abcdef..."
# и т.д.
```

## Решение проблем

### Сервис не запускается

1. Проверьте права доступа:
   ```bash
   ls -la /path/to/dev-monitorshik-test/main.py
   ```

2. Проверьте логи:
   ```bash
   sudo journalctl -u unified-monitor.service -n 50
   ```

3. Проверьте Python:
   ```bash
   /usr/bin/python3 --version
   ```

### Сервис запускается но сразу останавливается

Проверьте логи для ошибок:
```bash
sudo journalctl -u unified-monitor.service -f
```

Обычные причины:
- Ошибки в `.env` файле
- Отсутствие зависимостей Python
- Проблемы с путями к файлам

### База данных заблокирована

Если возникают ошибки блокировки БД:
1. Убедитесь, что используется только один экземпляр сервиса
2. Проверьте права на файл БД
3. Включен WAL mode (делается автоматически)

