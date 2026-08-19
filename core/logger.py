import logging
import sys
from datetime import datetime

class DebugConsoleFilter(logging.Filter):
    """
    Console log filter based on config.debug_mode:
    - If debug_mode is True: passes all log messages to console.
    - If debug_mode is False: passes only headers, account auth, TG bot auth, lot raising, messages, and warnings/errors.
    """
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            from config import config
            if getattr(config, "debug_mode", False):
                return True
        except Exception:
            return True

        if record.levelno >= logging.WARNING:
            return True

        msg = record.getMessage().lower()
        allowed_keywords = [
            "starting starvell", "assistant bot", "=========", "--------------",
            "авторизован", "telegrambot", "telegram bot",
            "autoraise", "авто-подняти", "подняти", "поднят", "поднятие",
            "chatrelay", "autoresponder", "сообщени", "отправка", "чат", "приветств"
        ]

        return any(kw in msg for kw in allowed_keywords)

def setup_logger(name: str = "StarvellAssistant", level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    if not logger.handlers:
        console_formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
            datefmt="%H:%M:%S"
        )
        if hasattr(sys.stdout, "reconfigure"):
            try:
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(console_formatter)
        stream_handler.addFilter(DebugConsoleFilter())
        logger.addHandler(stream_handler)
        
    return logger

logger = setup_logger()
