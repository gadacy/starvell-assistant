import os
import json
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

class Config(BaseModel):
    starvell_api_key: str = Field(default_factory=lambda: os.getenv("STARVELL_API_KEY", ""))
    starvell_user_id: str = Field(default_factory=lambda: os.getenv("STARVELL_USER_ID", ""))
    simulation_mode: bool = Field(default_factory=lambda: os.getenv("SIMULATION_MODE", "false").lower() == "true")
    debug_mode: bool = Field(default_factory=lambda: os.getenv("DEBUG_MODE", "false").lower() == "true")
    
    telegram_bot_token: str = Field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))
    telegram_admin_ids: list[int] = Field(default_factory=lambda: [
        int(x.strip()) for x in os.getenv("TELEGRAM_ADMIN_IDS", "").split(",") if x.strip().isdigit()
    ])

    watermark_enabled: bool = Field(default_factory=lambda: os.getenv("WATERMARK_ENABLED", "true").lower() == "true")
    watermark_text: str = Field(default_factory=lambda: os.getenv("WATERMARK_TEXT", "🤖 Отправлено через Starvell Assistant"))
    
    database_url: str = Field(default_factory=lambda: os.getenv("DATABASE_URL", "sqlite+aiosqlite:///starvell_bot.db"))

config_load_error: Optional[str] = None

def load_config() -> Config:
    global config_load_error
    config_file = BASE_DIR / "config.json"
    if config_file.exists():
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                content = f.read()
            if not content.strip():
                config_load_error = "Файл config.json пуст"
                return Config()
            data = json.loads(content)
            if not isinstance(data, dict):
                config_load_error = "Файл config.json не содержит JSON-объект"
                return Config()
            cfg = Config(**data)
            config_load_error = None
            return cfg
        except Exception as e:
            config_load_error = str(e)
            print(f"[Warning] Failed to load config.json: {e}. Falling back to env variables.")
    else:
        config_load_error = None

    return Config()

def save_config(config: Config) -> None:
    config_file = BASE_DIR / "config.json"
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(config.model_dump(), f, indent=2, ensure_ascii=False)

def check_config_status() -> tuple[bool, str, str]:
    """
    Checks whether the configuration is valid and ready to use.
    Returns:
        (is_valid: bool, status_code: str, message: str)
        status_code:
            - 'ok': configuration is valid and filled with credentials.
            - 'missing': config.json does not exist.
            - 'corrupted': config.json is empty, corrupted, unparseable, or has invalid schema.
            - 'empty': config.json exists and is valid JSON, but lacks credentials.
            - 'env_only': config.json missing, but credentials found in .env.
    """
    config_file = BASE_DIR / "config.json"

    if not config_file.exists():
        env_tg = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        env_admins = [int(x.strip()) for x in os.getenv("TELEGRAM_ADMIN_IDS", "").split(",") if x.strip().isdigit()]
        if env_tg and env_admins:
            try:
                env_cfg = Config()
                save_config(env_cfg)
                return True, "env_only", "Конфигурация получена из .env (файл config.json создан автоматически)."
            except Exception:
                return True, "env_only", "Конфигурация получена из переменных окружения (.env)."
        return False, "missing", "Файл конфигурации config.json отсутствует."

    try:
        content = config_file.read_text(encoding="utf-8").strip()
        if not content:
            return False, "corrupted", "Файл config.json пуст (0 байт)."
        data = json.loads(content)
        if not isinstance(data, dict):
            return False, "corrupted", "Файл config.json повреждён (не является JSON-объектом)."
        cfg = Config(**data)
    except json.JSONDecodeError as e:
        return False, "corrupted", f"Файл config.json повреждён (ошибка синтаксиса JSON: {e})."
    except Exception as e:
        return False, "corrupted", f"Файл config.json повреждён или содержит некорректные поля: {e}"

    if not cfg.telegram_bot_token.strip():
        return False, "empty", "В файле config.json не указан обязательный токен Telegram-бота."

    if not cfg.telegram_admin_ids:
        return False, "empty", "В файле config.json не указаны обязательные ID администраторов Telegram."

    return True, "ok", "Конфигурация корректна."

def reload_config() -> Config:
    """Reloads config from disk (.env and config.json) and updates singleton in-place."""
    load_dotenv(BASE_DIR / ".env", override=True)
    new_cfg = load_config()
    for field, val in new_cfg.model_dump().items():
        setattr(config, field, val)
    return config

config = load_config()

def _sync_env_admin_ids() -> None:
    """Synchronizes telegram_admin_ids into the .env file if it exists."""
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    try:
        content = env_file.read_text(encoding="utf-8")
        ids_str = ",".join(str(i) for i in config.telegram_admin_ids)
        lines = []
        replaced = False
        for line in content.splitlines():
            if line.startswith("TELEGRAM_ADMIN_IDS="):
                lines.append(f"TELEGRAM_ADMIN_IDS={ids_str}")
                replaced = True
            else:
                lines.append(line)
        if not replaced:
            lines.append(f"TELEGRAM_ADMIN_IDS={ids_str}")
        env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception:
        pass

def add_admin_id(admin_id: int) -> bool:
    """Adds a new Telegram user ID to the authorized admin list and persists the update."""
    if admin_id in config.telegram_admin_ids:
        return False
    config.telegram_admin_ids.append(admin_id)
    save_config(config)
    _sync_env_admin_ids()
    return True

def remove_admin_id(admin_id: int) -> bool:
    """Removes a Telegram user ID from the authorized admin list and persists the update."""
    if admin_id not in config.telegram_admin_ids:
        return False
    config.telegram_admin_ids.remove(admin_id)
    save_config(config)
    _sync_env_admin_ids()
    return True
