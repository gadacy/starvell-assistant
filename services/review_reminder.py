import asyncio
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy import select
from core.database.base import AsyncSessionLocal
from core.database.models import OrderHistory, BotSetting
from core.logger import logger
from starvell.client import StarvellClient

class ReviewReminderService:
    """
    Service to send review reminders to buyers N minutes after successful order delivery.
    """
    def __init__(self, client: StarvellClient, check_interval: int = 300, delay_minutes: int = 15):
        self.client = client
        self.check_interval = check_interval
        self.delay_minutes = delay_minutes
        self._is_running = False
        self._task: Optional[asyncio.Task] = None

    async def is_enabled(self) -> bool:
        async with AsyncSessionLocal() as session:
            res = await session.execute(
                select(BotSetting).where(BotSetting.key == "review_reminder_enabled")
            )
            setting = res.scalar_one_or_none()
            return setting.value.lower() == "true" if setting else True

    async def get_reminder_text(self) -> str:
        async with AsyncSessionLocal() as session:
            res = await session.execute(
                select(BotSetting).where(BotSetting.key == "review_reminder_text")
            )
            setting = res.scalar_one_or_none()
            if setting and setting.value:
                return setting.value
        return (
            "❤️ **Большое спасибо за покупку!**\n\n"
            "Если вам всё понравилось, пожалуйста, оставьте отзыв к заказу. "
            "Это очень помогает нашему магазину развиваться!"
        )

    async def start(self):
        if self._is_running:
            return
        self._is_running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("[ReviewReminder] Service started.")

    async def stop(self):
        self._is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("[ReviewReminder] Stopped.")

    async def _loop(self):
        while self._is_running:
            try:
                if await self.is_enabled():
                    await self.process_reminders()
            except Exception as e:
                logger.error(f"[ReviewReminder] Error in reminder loop: {e}")

            await asyncio.sleep(self.check_interval)

    async def process_reminders(self):
        threshold_time = datetime.utcnow() - timedelta(minutes=self.delay_minutes)
        reminder_text = await self.get_reminder_text()

        async with AsyncSessionLocal() as session:
            res = await session.execute(
                select(OrderHistory).where(
                    OrderHistory.status == "delivered",
                    OrderHistory.created_at <= threshold_time
                )
            )
            delivered_orders = res.scalars().all()

            for order in delivered_orders:
                chat_id = order.buyer_id
                logger.info(f"[ReviewReminder] Sending review reminder to buyer {order.buyer_name} for order {order.order_id}")
                sent_ok = await self.client.send_message(chat_id, reminder_text, is_auto=True)
                if sent_ok:
                    order.status = "completed"
            
            await session.commit()
