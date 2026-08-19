import os
import json
from pathlib import Path
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

def load_config() -> Config:
    config_file = BASE_DIR / "config.json"
    if config_file.exists():
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return Config(**data)
        except Exception as e:
            print(f"[Warning] Failed to load config.json: {e}. Falling back to env variables.")
    
    return Config()

def save_config(config: Config) -> None:
    config_file = BASE_DIR / "config.json"
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(config.model_dump(), f, indent=2, ensure_ascii=False)

config = load_config()
