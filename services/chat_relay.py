import html
from datetime import datetime
from typing import Optional, Dict
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select
from core.database.base import AsyncSessionLocal
from core.database.models import BotSetting, SeenChat
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
        self.seen_chats: Dict[str, datetime] = {}

    async def init_seen_chats(self):
        """
        Loads already seen chats and last activity from database, and seeds existing chats from Starvell API
        so greetings are never sent to pre-existing chats unexpectedly.
        """
        # 1. Load seen chats from DB
        try:
            async with AsyncSessionLocal() as session:
                res = await session.execute(select(SeenChat))
                db_chats = res.scalars().all()
                for c in db_chats:
                    self.seen_chats[str(c.chat_id)] = c.last_seen_at or c.created_at or datetime.utcnow()
            logger.info(f"[ChatRelay] Loaded {len(self.seen_chats)} seen chats from database.")
        except Exception as e:
            logger.error(f"[ChatRelay] Error loading seen chats from DB: {e}")

        # 2. Seed existing chats from Starvell API
        try:
            chats = await self.client.get_chats()
            new_seen_count = 0
            now = datetime.utcnow()
            async with AsyncSessionLocal() as session:
                for chat in chats:
                    if isinstance(chat, dict):
                        chat_id = str(chat.get("id", ""))
                        if chat_id and chat_id not in self.seen_chats:
                            self.seen_chats[chat_id] = now
                            session.add(SeenChat(chat_id=chat_id, created_at=now, last_seen_at=now))
                            new_seen_count += 1
                if new_seen_count > 0:
                    await session.commit()
            if new_seen_count > 0:
                logger.info(f"[ChatRelay] Seeded {new_seen_count} pre-existing chats from Starvell into database.")
        except Exception as e:
            logger.error(f"[ChatRelay] Error seeding existing chats from Starvell API: {e}")

    async def update_chat_activity(self, chat_id: str, last_seen: Optional[datetime] = None):
        """
        Updates last activity timestamp for a chat in memory and database.
        """
        if not chat_id:
            return

        now = last_seen or datetime.utcnow()
        self.seen_chats[chat_id] = now
        try:
            async with AsyncSessionLocal() as session:
                res = await session.execute(select(SeenChat).where(SeenChat.chat_id == chat_id))
                record = res.scalar_one_or_none()
                if record:
                    record.last_seen_at = now
                else:
                    session.add(SeenChat(chat_id=chat_id, created_at=now, last_seen_at=now))
                await session.commit()
        except Exception as e:
            logger.error(f"[ChatRelay] Error updating activity for chat {chat_id} in DB: {e}")

    async def mark_chat_seen(self, chat_id: str):
        """
        Backwards-compatible helper to update chat activity.
        """
        await self.update_chat_activity(chat_id)

    async def is_greeting_enabled(self) -> bool:
        async with AsyncSessionLocal() as session:
            res = await session.execute(
                select(BotSetting).where(BotSetting.key == "auto_greeting_enabled")
            )
            setting = res.scalar_one_or_none()
            return setting.value.lower() == "true" if setting else True

    async def get_greeting_mode(self) -> str:
        """Returns 'once' or 'cooldown'"""
        async with AsyncSessionLocal() as session:
            res = await session.execute(
                select(BotSetting).where(BotSetting.key == "auto_greeting_mode")
            )
            setting = res.scalar_one_or_none()
            return setting.value.lower() if setting and setting.value else "once"

    async def get_cooldown_hours(self) -> float:
        """Returns inactivity threshold in hours (default 168.0 = 7 days)"""
        async with AsyncSessionLocal() as session:
            res = await session.execute(
                select(BotSetting).where(BotSetting.key == "auto_greeting_cooldown_hours")
            )
            setting = res.scalar_one_or_none()
            if setting and setting.value:
                try:
                    return float(setting.value)
                except ValueError:
                    pass
        return 168.0

    async def get_greeting_text(self) -> str:
        async with AsyncSessionLocal() as session:
            res = await session.execute(
                select(BotSetting).where(BotSetting.key == "auto_greeting_text")
            )
            setting = res.scalar_one_or_none()
            if setting and setting.value:
                return setting.value
        return "👋 **Здравствуйте, {buyer_name}!** Рады видеть вас в нашем магазине. Чем можем помочь?"

    async def get_regreeting_text(self) -> str:
        async with AsyncSessionLocal() as session:
            res = await session.execute(
                select(BotSetting).where(BotSetting.key == "auto_regreeting_text")
            )
            setting = res.scalar_one_or_none()
            if setting and setting.value:
                return setting.value
        return "👋 **С возвращением, {buyer_name}!** Снова рады видеть вас. Чем можем помочь?"

    async def process_incoming_message(self, message: StarvellMessage, order: Optional[StarvellOrder] = None):
        # 1. First Message & Cooldown Greeting Check
        chat_id = str(message.chat_id or message.sender_id or "")
        now = datetime.utcnow()

        if order is not None:
            await self.update_chat_activity(chat_id, now)
        else:
            if await self.is_greeting_enabled():
                if chat_id not in self.seen_chats:
                    # Brand new chat: send primary greeting
                    greeting_template = await self.get_greeting_text()
                    greeting_text = greeting_template.replace("{buyer_name}", message.sender_name or "Покупатель")
                    logger.info(f"[ChatRelay] Sending welcome greeting to new buyer {message.sender_name} (Chat {chat_id})")
                    await self.client.send_message(chat_id, greeting_text, is_auto=True)
                else:
                    # Existing chat: check if mode is 'cooldown' and inactivity threshold passed
                    mode = await self.get_greeting_mode()
                    if mode == "cooldown":
                        last_activity = self.seen_chats.get(chat_id, now)
                        hours_passed = (now - last_activity).total_seconds() / 3600.0
                        cooldown_hours = await self.get_cooldown_hours()
                        if hours_passed >= cooldown_hours:
                            regreeting_template = await self.get_regreeting_text()
                            greeting_text = regreeting_template.replace("{buyer_name}", message.sender_name or "Покупатель")
                            logger.info(
                                f"[ChatRelay] Inactivity cooldown passed ({hours_passed:.1f}h >= {cooldown_hours}h). "
                                f"Sending re-greeting to buyer {message.sender_name} (Chat {chat_id})"
                            )
                            await self.client.send_message(chat_id, greeting_text, is_auto=True)

            # Update last activity for this chat
            await self.update_chat_activity(chat_id, now)

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
        profile_url = f"https://starvell.com/profile/{sender_name}" if sender_name != "Покупатель" else "https://starvell.com"

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

