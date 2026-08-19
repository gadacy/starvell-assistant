import html
from typing import Optional, Set
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select
from core.database.base import AsyncSessionLocal
from core.database.models import BotSetting
from core.logger import logger
from starvell.client import StarvellClient
from starvell.models import StarvellMessage, StarvellOrder
from tg_bot.bot import get_bot
from config import config

class ChatRelayService:
    """
    Relays messages between Starvell chat and Telegram admin bot.
    Allows admins to read and respond to Starvell buyers directly from Telegram!
    """
    def __init__(self, client: StarvellClient):
        self.client = client
        self.seen_buyers: Set[str] = set()

    async def is_greeting_enabled(self) -> bool:
        async with AsyncSessionLocal() as session:
            res = await session.execute(
                select(BotSetting).where(BotSetting.key == "auto_greeting_enabled")
            )
            setting = res.scalar_one_or_none()
            return setting.value.lower() == "true" if setting else True

    async def get_greeting_text(self) -> str:
        async with AsyncSessionLocal() as session:
            res = await session.execute(
                select(BotSetting).where(BotSetting.key == "auto_greeting_text")
            )
            setting = res.scalar_one_or_none()
            if setting and setting.value:
                return setting.value
        return "👋 **Здравствуйте, {buyer_name}!** Рады видеть вас в нашем магазине. Чем можем помочь?"

    async def process_incoming_message(self, message: StarvellMessage, order: Optional[StarvellOrder] = None):
        # 1. First Message Greeting Check
        chat_id = message.chat_id or message.sender_id
        
        # If an order exists or is passed, mark chat as seen so greeting won't trigger for instant purchase
        if order is not None:
            self.seen_buyers.add(chat_id)
        elif chat_id not in self.seen_buyers:
            self.seen_buyers.add(chat_id)
            if await self.is_greeting_enabled():
                greeting_template = await self.get_greeting_text()
                greeting_text = greeting_template.replace("{buyer_name}", message.sender_name or "Покупатель")
                logger.info(f"[ChatRelay] Sending welcome greeting to buyer {message.sender_name} (Chat {chat_id})")
                await self.client.send_message(chat_id, greeting_text, is_auto=True)

        # 2. Check notification settings for chat messages
        async with AsyncSessionLocal() as session:
            res = await session.execute(
                select(BotSetting).where(BotSetting.key == "notify_chat_messages")
            )
            setting = res.scalar_one_or_none()
            notify_enabled = setting.value.lower() == "true" if setting else True

        if not notify_enabled:
            logger.info(f"[ChatRelay] Chat message notification is disabled in settings. Skipping forwarding.")
            return

        # 3. Forward Message to Telegram Admin
        bot_instance = get_bot()
        if not bot_instance:
            logger.warning("[ChatRelay] Telegram bot is not initialized. Cannot forward message.")
            return

        if not config.telegram_admin_ids:
            logger.warning("[ChatRelay] TELEGRAM_ADMIN_IDS is empty in config. Cannot forward message.")
            return

        sender_name = message.sender_name or "Покупатель"
        safe_sender = html.escape(sender_name)
        safe_sender_id = html.escape(str(message.sender_id))
        safe_msg_text = html.escape(message.text or "")
        profile_url = f"https://starvell.com/users/{sender_name}" if sender_name != "Покупатель" else "https://starvell.com"

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✍️ Ответить",
                    callback_data=f"reply_chat_{chat_id}"
                ),
                InlineKeyboardButton(
                    text="⚡ Быстрые ответы",
                    callback_data=f"quick_replies_{chat_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="👤 Посмотреть профиль",
                    url=profile_url
                )
            ]
        ])

        order_str = f" (Заказ #{html.escape(str(order.id))})" if order else ""
        notification_text = (
            f"💬 <b>Новое сообщение от {safe_sender}</b>{order_str}:\n"
            f"{safe_msg_text}"
        )

        for admin_id in config.telegram_admin_ids:
            try:
                await bot_instance.send_message(admin_id, notification_text, reply_markup=kb, parse_mode="HTML")
                logger.info(f"[ChatRelay] Message from {sender_name} (chat {chat_id}) successfully forwarded to TG admin {admin_id}")
            except Exception as e:
                logger.error(f"[ChatRelay] Error sending HTML message to admin {admin_id}: {e}. Trying plain text fallback...")
                try:
                    plain_text = (
                        f"💬 Новое сообщение от {sender_name}:\n"
                        f"{message.text}"
                    )
                    await bot_instance.send_message(admin_id, plain_text, reply_markup=kb)
                    logger.info(f"[ChatRelay] Plain text message successfully forwarded to TG admin {admin_id}")
                except Exception as ex:
                    logger.error(f"[ChatRelay] Error forwarding plain message to admin {admin_id}: {ex}")

