#!/bin/bash

###############################################################################
# Deploy Script для Unified Monitor
# Автоматическое развертывание на VPS сервере
###############################################################################

set -e  # Останавливаться при ошибках

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Функции для вывода
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
}

# Проверка запуска от root
if [ "$EUID" -eq 0 ]; then 
    print_error "Не запускайте этот скрипт от root!"
    print_info "Используйте обычного пользователя с sudo правами"
    exit 1
fi

print_header "Unified Monitor - Deployment Script"

# Проверка операционной системы
if ! command -v apt &> /dev/null; then
    print_error "Этот скрипт предназначен для Ubuntu/Debian"
    exit 1
fi

# Определение директории проекта
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
print_info "Директория проекта: $PROJECT_DIR"

# Шаг 1: Обновление системы
print_header "Шаг 1: Обновление системы"
print_info "Обновление списка пакетов..."
sudo apt update

read -p "Обновить все пакеты системы? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    sudo apt upgrade -y
    print_success "Система обновлена"
else
    print_warning "Обновление системы пропущено"
fi

# Шаг 2: Установка зависимостей
print_header "Шаг 2: Установка системных зависимостей"
print_info "Установка Python, pip, venv, git, sqlite3..."
sudo apt install -y python3 python3-pip python3-venv git sqlite3

print_success "Системные зависимости установлены"

# Шаг 3: Создание виртуального окружения
print_header "Шаг 3: Настройка виртуального окружения"

if [ -d "$PROJECT_DIR/venv" ]; then
    print_warning "Виртуальное окружение уже существует"
    read -p "Пересоздать? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$PROJECT_DIR/venv"
        print_info "Старое окружение удалено"
    fi
fi

if [ ! -d "$PROJECT_DIR/venv" ]; then
    print_info "Создание виртуального окружения..."
    python3 -m venv "$PROJECT_DIR/venv"
    print_success "Виртуальное окружение создано"
fi

# Активация виртуального окружения
source "$PROJECT_DIR/venv/bin/activate"

# Обновление pip
print_info "Обновление pip..."
pip install --upgrade pip

# Установка Python зависимостей
print_info "Установка Python зависимостей..."
pip install -r "$PROJECT_DIR/requirements.txt"
print_success "Python зависимости установлены"

# Шаг 4: Конфигурация
print_header "Шаг 4: Конфигурация"

if [ ! -f "$PROJECT_DIR/.env" ]; then
    print_warning "Файл .env не найден"
    if [ -f "$PROJECT_DIR/env.example" ]; then
        print_info "Копирование env.example -> .env"
        cp "$PROJECT_DIR/env.example" "$PROJECT_DIR/.env"
        print_warning "ВАЖНО: Отредактируйте .env файл перед запуском!"
        print_info "nano $PROJECT_DIR/.env"
    else
        print_error "Файл env.example не найден!"
        exit 1
    fi
else
    print_success "Файл .env существует"
fi

# Шаг 5: Создание директорий
print_header "Шаг 5: Создание необходимых директорий"

mkdir -p "$PROJECT_DIR/logs"
mkdir -p "$PROJECT_DIR/backups"
print_success "Директории созданы"

# Шаг 6: Проверка работоспособности
print_header "Шаг 6: Проверка конфигурации"

print_info "Проверка .env файла..."
if grep -q "your_" "$PROJECT_DIR/.env"; then
    print_warning "В .env найдены значения по умолчанию (your_*)"
    print_warning "Пожалуйста, заполните все параметры в .env"
fi

# Шаг 7: Настройка systemd
print_header "Шаг 7: Настройка systemd сервисов"

read -p "Установить systemd сервисы? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    
    # Получаем имя текущего пользователя
    CURRENT_USER=$(whoami)
    CURRENT_HOME=$(eval echo ~$CURRENT_USER)
    
    print_info "Настройка сервисов для пользователя: $CURRENT_USER"
    print_info "Домашняя директория: $CURRENT_HOME"
    
    # Копируем и модифицируем systemd юниты
    for service_file in "$PROJECT_DIR/deploy"/*.service; do
        if [ -f "$service_file" ]; then
            service_name=$(basename "$service_file")
            print_info "Настройка $service_name..."
            
            # Создаем временный файл с заменой путей
            temp_file=$(mktemp)
            sed "s|YOUR_USER|$CURRENT_USER|g; s|/home/YOUR_USER|$CURRENT_HOME|g; s|dev-monitorshik-test|unified-monitor|g" "$service_file" > "$temp_file"
            
            # Копируем в systemd
            sudo cp "$temp_file" "/etc/systemd/system/$service_name"
            rm "$temp_file"
            
            print_success "$service_name настроен"
        fi
    done
    
    # Перезагружаем systemd
    print_info "Перезагрузка systemd daemon..."
    sudo systemctl daemon-reload
    
    print_success "Systemd сервисы настроены"
    
    # Предлагаем включить сервисы
    read -p "Включить автозапуск сервисов? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        sudo systemctl enable unified-monitor
        sudo systemctl enable sentiment-api
        sudo systemctl enable sentiment-dashboard
        print_success "Автозапуск включен"
    fi
    
else
    print_warning "Установка systemd сервисов пропущена"
fi

# Шаг 8: Настройка Nginx (опционально)
print_header "Шаг 8: Настройка Nginx (опционально)"

read -p "Установить и настроить Nginx? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    
    # Установка Nginx
    if ! command -v nginx &> /dev/null; then
        print_info "Установка Nginx..."
        sudo apt install -y nginx
    else
        print_success "Nginx уже установлен"
    fi
    
    # Запрос доменных имен
    read -p "Введите домен для API (или нажмите Enter для localhost): " API_DOMAIN
    read -p "Введите домен для Dashboard (или нажмите Enter для localhost): " DASHBOARD_DOMAIN
    
    if [ -z "$API_DOMAIN" ]; then
        API_DOMAIN="localhost"
    fi
    
    if [ -z "$DASHBOARD_DOMAIN" ]; then
        DASHBOARD_DOMAIN="localhost"
    fi
    
    # Создание конфигурации Nginx
    print_info "Создание конфигурации Nginx..."
    sudo tee /etc/nginx/sites-available/unified-monitor > /dev/null <<EOF
# API сервер
server {
    listen 80;
    server_name $API_DOMAIN;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}

# Dashboard
server {
    listen 80;
    server_name $DASHBOARD_DOMAIN;

    location / {
        proxy_pass http://localhost:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 86400;
    }
}
EOF
    
    # Активация конфигурации
    sudo ln -sf /etc/nginx/sites-available/unified-monitor /etc/nginx/sites-enabled/
    
    # Проверка конфигурации
    if sudo nginx -t; then
        print_success "Конфигурация Nginx валидна"
        sudo systemctl restart nginx
        print_success "Nginx перезапущен"
    else
        print_error "Ошибка в конфигурации Nginx"
    fi
    
    # Предложение установить SSL
    if [ "$API_DOMAIN" != "localhost" ] && [ "$DASHBOARD_DOMAIN" != "localhost" ]; then
        read -p "Установить SSL сертификаты через Let's Encrypt? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            sudo apt install -y certbot python3-certbot-nginx
            sudo certbot --nginx -d "$API_DOMAIN" -d "$DASHBOARD_DOMAIN"
            print_success "SSL сертификаты установлены"
        fi
    fi
    
else
    print_warning "Настройка Nginx пропущена"
fi

# Шаг 9: Настройка Firewall
print_header "Шаг 9: Настройка Firewall"

read -p "Настроить UFW firewall? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    
    if ! command -v ufw &> /dev/null; then
        print_info "Установка UFW..."
        sudo apt install -y ufw
    fi
    
    print_info "Настройка правил firewall..."
    sudo ufw allow ssh
    
    if command -v nginx &> /dev/null; then
        sudo ufw allow 'Nginx Full'
    else
        sudo ufw allow 8000/tcp
        sudo ufw allow 8501/tcp
    fi
    
    print_warning "Firewall будет включен. Убедитесь что SSH доступ разрешен!"
    read -p "Включить firewall? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        sudo ufw --force enable
        print_success "Firewall включен"
        sudo ufw status
    fi
    
else
    print_warning "Настройка firewall пропущена"
fi

# Шаг 10: Финальная проверка и запуск
print_header "Шаг 10: Запуск сервисов"

read -p "Запустить все сервисы сейчас? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    
    print_info "Запуск сервисов..."
    
    sudo systemctl start unified-monitor
    sleep 2
    
    sudo systemctl start sentiment-api
    sleep 2
    
    sudo systemctl start sentiment-dashboard
    sleep 2
    
    print_success "Сервисы запущены"
    
    echo ""
    print_info "Статус сервисов:"
    sudo systemctl status unified-monitor --no-pager -l | head -n 5
    sudo systemctl status sentiment-api --no-pager -l | head -n 5
    sudo systemctl status sentiment-dashboard --no-pager -l | head -n 5
    
else
    print_warning "Запуск сервисов пропущен"
fi

# Итоги
print_header "Развертывание завершено!"

echo ""
print_success "Unified Monitor успешно развернут!"
echo ""
print_info "Что дальше:"
echo ""
echo "  1. Проверьте и отредактируйте .env файл:"
echo "     nano $PROJECT_DIR/.env"
echo ""
echo "  2. Перезапустите сервисы после редактирования .env:"
echo "     sudo systemctl restart unified-monitor sentiment-api sentiment-dashboard"
echo ""
echo "  3. Проверьте статус сервисов:"
echo "     sudo systemctl status unified-monitor"
echo "     sudo systemctl status sentiment-api"
echo "     sudo systemctl status sentiment-dashboard"
echo ""
echo "  4. Просмотрите логи:"
echo "     sudo journalctl -u unified-monitor -f"
echo "     tail -f $PROJECT_DIR/logs/unified-monitor.log"
echo ""
echo "  5. Откройте Dashboard в браузере:"
if command -v nginx &> /dev/null && [ ! -z "$DASHBOARD_DOMAIN" ]; then
    echo "     http://$DASHBOARD_DOMAIN"
else
    echo "     http://$(hostname -I | awk '{print $1}'):8501"
fi
echo ""
print_info "Документация: $PROJECT_DIR/DEPLOYMENT.md"
echo ""

deactivate 2>/dev/null || true


