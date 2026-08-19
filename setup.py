import os
import sys
import json
import asyncio
import httpx
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

from core.banner import print_banner

def validate_telegram_token(token: str) -> tuple[bool, str]:
    if not token or ":" not in token:
        return False, "Неверный формат токена"
    try:
        res = httpx.get(f"https://api.telegram.org/bot{token}/getMe", timeout=5.0)
        data = res.json()
        if data.get("ok"):
            bot_username = data["result"].get("username", "Bot")
            return True, f"Успешно! Имя бота: @{bot_username}"
        else:
            return False, f"Ошибка Telegram API: {data.get('description')}"
    except Exception as e:
        return False, f" Ошибка соединения: {e}"

def run_setup():
    print_banner()

    print("ℹ️ Этот скрипт поможет вам настроить файлы конфигурации (.env и config.json).\n")

    # 1. Starvell Session Cookie / Token
    print("----------------------------------------------------------------")
    print("1️⃣ Настройка Авторизации Starvell (Сессионная Кука / Токен)")
    print("----------------------------------------------------------------")
    print("💡 У Starvell нет официального API-ключа. Бот использует авторизационную куку сессии.")
    print("📌 Как получить куку/токен из браузера:")
    print("   1. Зайдите на сайт Starvell.com и авторизуйтесь в свой аккаунт.")
    print("   2. Нажмите F12 (DevTools) ➔ Вкладка 'Приложение' (Application) или 'Storage'.")
    print("   3. Раздел 'Куки' (Cookies) ➔ https://starvell.com")
    print("   4. Скопируйте значение (Value) куки: session, remember_web_*, PHPSESSID или token.")
    print("   (Или из заголовка Authorization / Cookie любого запроса на вкладке 'Сеть' / Network).\n")
    
    starvell_key = input("🔑 Вставьте значение куки/токена Starvell (или нажмите Enter для тестового режима): ").strip()
    starvell_user_id = ""
    if starvell_key:
        starvell_user_id = input("👤 Введите ваш Starvell User ID (опционально): ").strip()
    else:
        print("⚠️ Токен не введен. Бот будет запущен в SIMULATION / DRY-RUN режиме.\n")

    # 2. Telegram Bot Token
    print("----------------------------------------------------------------")
    print("2️⃣ Настройка Telegram Бота (управление и уведомления)")
    print("----------------------------------------------------------------")
    print("💡 Токен можно получить у @BotFather в Telegram.")
    
    tg_token = ""
    while True:
        tg_token = input("🤖 Введите Telegram Bot Token: ").strip()
        if not tg_token:
            confirm = input("⚠️ Токен бота не введен. Пропустить настройку Telegram? (y/N): ").strip().lower()
            if confirm == "y":
                break
            continue
        
        valid, status_msg = validate_telegram_token(tg_token)
        print(f"   {status_msg}")
        if valid:
            break
        else:
            retry = input("   Попробовать ввести снова? (Y/n): ").strip().lower()
            if retry == "n":
                break

    # 3. Telegram Admin IDs
    tg_admin_ids = ""
    if tg_token:
        print("\n💡 ID своего аккаунта Telegram можно узнать у ботов @userinfobot или @myidbot.")
        tg_admin_ids = input("👑 Введите ваш численный Telegram ID (если несколько, через запятую): ").strip()

    # Save to .env
    env_content = f"""# Starvell Authentication
STARVELL_API_KEY={starvell_key}
STARVELL_USER_ID={starvell_user_id}

# Telegram Bot Config
TELEGRAM_BOT_TOKEN={tg_token}
TELEGRAM_ADMIN_IDS={tg_admin_ids}

# Database
DATABASE_URL=sqlite+aiosqlite:///starvell_bot.db
"""

    env_path = BASE_DIR / ".env"
    with open(env_path, "w", encoding="utf-8") as f:
        f.write(env_content)

    # Save to config.json
    admin_list = []
    if tg_admin_ids:
        admin_list = [int(x.strip()) for x in tg_admin_ids.split(",") if x.strip().isdigit()]

    config_data = {
        "starvell_api_key": starvell_key,
        "starvell_user_id": starvell_user_id,
        "telegram_bot_token": tg_token,
        "telegram_admin_ids": admin_list,
        "database_url": "sqlite+aiosqlite:///starvell_bot.db"
    }

    config_path = BASE_DIR / "config.json"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=2, ensure_ascii=False)

    print("\n================================================================")
    print("✅ НАСТРОЙКА УСПЕШНО ЗАВЕРШЕНА!")
    print("================================================================")
    print(f"📁 Создан файл .env и config.json")

    # Initialize DB
    sys.path.insert(0, str(BASE_DIR))
    from core.database.base import init_db
    print("⚙️ Инициализация базы данных SQLite...")
    asyncio.run(init_db())
    print("✅ База данных готова к работе.")

    start_now = input("\n🚀 Запустить бота прям сейчас? (Y/n): ").strip().lower()
    if start_now != "n":
        print("\nЗапуск main.py...\n")
        from main import main
        asyncio.run(main())

if __name__ == "__main__":
    run_setup()
