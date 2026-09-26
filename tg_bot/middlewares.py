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
                    await event.answer("❌ <b>Доступ запрещен.</b> Вы не являетесь администратором бота.", parse_mode="HTML")
                elif isinstance(event, CallbackQuery):
                    await event.answer("❌ Доступ запрещен.", show_alert=True)
                return None
        else:
            logger.error("[Security] TELEGRAM_ADMIN_IDS is empty; access is disabled until an administrator is configured.")
            if isinstance(event, Message):
                await event.answer("❌ Доступ запрещен: администратор бота не настроен.")
            elif isinstance(event, CallbackQuery):
                await event.answer("❌ Администратор бота не настроен.", show_alert=True)
            return None

        return await handler(event, data)


class ChatNavigationMiddleware(BaseMiddleware):
    """Leaving the chat UI must not leave a hidden recipient for subsequent text."""
    async def __call__(self, handler, event, data):
        from tg_bot.handlers.chat import ChatReplyState

        state = data.get("state")
        if state and await state.get_state() == ChatReplyState.active.state:
            leave_chat = False
            if isinstance(event, CallbackQuery):
                callback = event.data or ""
                leave_chat = not callback.startswith(("reply_chat_", "quick_replies_", "send_qr_", "close_starvell_chat"))
            elif isinstance(event, Message):
                text = event.text or ""
                command = text.split(maxsplit=1)[0].split("@", 1)[0] if text else ""
                leave_chat = command.startswith("/") and command != "/cancel"
            if leave_chat:
                await state.clear()
        return await handler(event, data)
