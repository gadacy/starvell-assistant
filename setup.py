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

def run_setup(standalone: bool = True) -> bool:
    """
    Runs the setup wizard to configure .env and config.json.

    :param standalone: If True, script was launched independently (python setup.py).
                       If False, script was invoked directly inside main.py window.
    :return: True if setup completed successfully, False otherwise.
    """
    if not sys.stdin.isatty():
        print("❌ [Setup] Ошибка: Мастер настройки требует интерактивного терминала (TTY).")
        print("   Пожалуйста, запустите настройку вручную в интерактивной консоли или настройте config.json заранее.")
        return False

    try:
        print_banner()

        if standalone:
            print("ℹ️ Этот скрипт поможет вам настроить файлы конфигурации (.env и config.json).\n")
        else:
            print("🛠️ Встроенный мастер первоначальной настройки Starvell Assistant\n")

        # Read existing config if present to preserve non-credential settings
        existing_data = {}
        config_path = BASE_DIR / "config.json"
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    parsed = json.load(f)
                    if isinstance(parsed, dict):
                        existing_data = parsed
            except Exception:
                pass

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

        # 2. Telegram Bot Token (Mandatory)
        print("----------------------------------------------------------------")
        print("2️⃣ Настройка Telegram Бота (ОБЯЗАТЕЛЬНО)")
        print("----------------------------------------------------------------")
        print("💡 Токен бота необходим для управления ботом и получения уведомлений.")
        print("💡 Получить токен можно у официального бота @BotFather в Telegram.\n")

        tg_token = ""
        while True:
            tg_token = input("🤖 Введите Telegram Bot Token: ").strip()
            if not tg_token:
                print("⚠️ Токен Telegram-бота обязателен! Настройку нельзя пропустить.\n")
                continue

            valid, status_msg = validate_telegram_token(tg_token)
            print(f"   {status_msg}")
            if valid:
                break
            else:
                print("⚠️ Указан недействительный токен. Попробуйте ввести корректный токен заново.\n")

        # 3. Telegram Admin IDs (Mandatory)
        print("----------------------------------------------------------------")
        print("3️⃣ Настройка Администратора Telegram (ОБЯЗАТЕЛЬНО)")
        print("----------------------------------------------------------------")
        print("💡 ID вашего аккаунта необходим для доступа к панели управления ботом.")
        print("💡 Узнать свой ID можно у ботов @userinfobot или @myidbot в Telegram.\n")

        admin_list = []
        tg_admin_ids = ""
        while True:
            tg_admin_ids = input("👑 Введите ваш численный Telegram ID (если несколько, через запятую): ").strip()
            if not tg_admin_ids:
                print("⚠️ Telegram ID администратора обязателен! Настройку нельзя пропустить.\n")
                continue

            admin_list = [int(x.strip()) for x in tg_admin_ids.split(",") if x.strip().isdigit()]
            if not admin_list:
                print("⚠️ Неверный формат ID. Введите число (например: 123456789 или 123456789, 987654321).\n")
                continue
            break

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
        config_data = {
            "starvell_api_key": starvell_key,
            "starvell_user_id": starvell_user_id,
            "simulation_mode": not bool(starvell_key),
            "debug_mode": existing_data.get("debug_mode", False),
            "telegram_bot_token": tg_token,
            "telegram_admin_ids": admin_list,
            "watermark_enabled": existing_data.get("watermark_enabled", True),
            "watermark_text": existing_data.get("watermark_text", "🤖 Отправлено через Starvell Assistant"),
            "database_url": existing_data.get("database_url", "sqlite+aiosqlite:///starvell_bot.db")
        }

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)

        # Update in-memory configuration singleton
        try:
            import config
            config.reload_config()
        except Exception:
            pass

        print("\n================================================================")
        print("✅ НАСТРОЙКА УСПЕШНО ЗАВЕРШЕНА!")
        print("================================================================")
        print("📁 Создан файл .env и config.json")

        # Initialize DB safely
        sys.path.insert(0, str(BASE_DIR))
        from core.database.base import init_db
        print("⚙️ Инициализация базы данных SQLite...")

        loop = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # In an active event loop, database will be initialized by main.py
            print("✅ База данных будет подключена при старте служб.")
        else:
            asyncio.run(init_db())
            print("✅ База данных готова к работе.")

        if standalone:
            start_now = input("\n🚀 Запустить бота прям сейчас? (Y/n): ").strip().lower()
            if start_now != "n":
                print("\nЗапуск main.py...\n")
                from main import main
                asyncio.run(main())
        else:
            print("\n🚀 Запуск служб бота в этом же окне...\n")

        return True

    except (KeyboardInterrupt, EOFError):
        print("\n\n❌ Настройка прервана пользователем.")
        return False

if __name__ == "__main__":
    run_setup(standalone=True)
