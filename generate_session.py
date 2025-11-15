#!/usr/bin/env python3
"""
Скрипт для генерации StringSession для Telegram
Запустите этот скрипт ОДИН РАЗ локально для получения StringSession
"""

import asyncio
from telethon.sync import TelegramClient
from telethon.sessions import StringSession

def main():
    print("=" * 50)
    print("Генерация StringSession для Telegram")
    print("=" * 50)
    print()
    print("📌 Получите API ID и API Hash на https://my.telegram.org")
    print()
    
    try:
        api_id = int(input("Введите ваш API ID: ").strip())
        api_hash = input("Введите ваш API Hash: ").strip()
    except ValueError:
        print("❌ Ошибка: API ID должен быть числом")
        return
    
    if not api_hash:
        print("❌ Ошибка: API Hash не может быть пустым")
        return
    
    print()
    print("🔐 Сейчас откроется авторизация в Telegram...")
    print("📱 Вам придет код подтверждения - введите его")
    print()
    
    try:
        with TelegramClient(StringSession(), api_id, api_hash) as client:
            print()
            print("=" * 50)
            print("✅ Авторизация успешна!")
            print("=" * 50)
            print()
            print("📋 Ваш StringSession:")
            print()
            session_string = client.session.save()
            print(session_string)
            print()
            print("=" * 50)
            print("⚠️  ВАЖНО:")
            print("  1. Скопируйте эту строку и сохраните в безопасном месте")
            print("  2. Используйте её в переменной TG_STRING_SESSION")
            print("  3. НЕ делитесь этой строкой ни с кем!")
            print("  4. Она даёт полный доступ к вашему Telegram аккаунту")
            print("=" * 50)
            print()
            
            # Опционально: сохранить в файл
            save = input("💾 Сохранить StringSession в файл? (y/n): ").lower()
            if save == 'y':
                with open("string_session.txt", "w") as f:
                    f.write(session_string)
                print("✅ Сохранено в файл string_session.txt")
                print("⚠️  НЕ добавляйте этот файл в Git!")
    
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return

if __name__ == "__main__":
    main()


