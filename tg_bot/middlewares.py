from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from config import config
from core.logger import logger

class AdminAuthMiddleware(BaseMiddleware):
    """
    Global Middleware to enforce admin whitelist check.
    If the user sending a message or callback query is NOT in config.telegram_admin_ids,
    their updates are completely ignored/blocked.
    """
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user_id = None
        if isinstance(event, Message) and event.from_user:
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery) and event.from_user:
            user_id = event.from_user.id

        if user_id is None:
            return None

        admin_ids = config.telegram_admin_ids
        if admin_ids:
            if user_id not in admin_ids:
                logger.warning(f"[Security] Access BLOCKED for unauthorized Telegram user ID: {user_id}")
                if isinstance(event, Message):
                    await event.answer("❌ **Доступ запрещен.** Вы не являетесь администратором бота.", parse_mode="Markdown")
                elif isinstance(event, CallbackQuery):
                    await event.answer("❌ Доступ запрещен.", show_alert=True)
                return None
        else:
            logger.warning(f"[Security] TELEGRAM_ADMIN_IDS is empty in config. Allowing user {user_id}.")

        return await handler(event, data)
