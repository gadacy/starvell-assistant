import asyncio
from typing import Optional, Dict, Any, List
from sqlalchemy import select
from core.database.base import AsyncSessionLocal
from core.database.models import BotSetting
from core.logger import logger
from starvell.client import StarvellClient

class AutoRaiseService:
    """
    Background loop for auto-raising (bumping) lots on Starvell.
    """
    def __init__(self, client: StarvellClient, interval_seconds: int = 1800):
        self.client = client
        self.interval_seconds = interval_seconds
        self._is_running = False
        self._task: Optional[asyncio.Task] = None

    async def is_enabled(self) -> bool:
        async with AsyncSessionLocal() as session:
            res = await session.execute(
                select(BotSetting).where(BotSetting.key == "auto_raise_enabled")
            )
            setting = res.scalar_one_or_none()
            if setting and setting.value.lower() == "false":
                return False
            return True

    async def start(self):
        if self._is_running:
            return
        self._is_running = True
        self._task = asyncio.create_task(self._loop())
        logger.info(f"[AutoRaiseService] Auto-raise service started (interval={self.interval_seconds}s).")

    async def stop(self):
        self._is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("[AutoRaiseService] Stopped.")

    async def _loop(self):
        while self._is_running:
            try:
                if await self.is_enabled():
                    result = await self.client.raise_lots()
                    if isinstance(result, dict):
                        raised = result.get("raised", [])
                        cooldowns = result.get("cooldowns", [])
                        if raised:
                            logger.info(f"[AutoRaiseService] ✅ Успешно подняты категории: {raised}")
                            async with AsyncSessionLocal() as session:
                                res_n = await session.execute(select(BotSetting).where(BotSetting.key == "notify_auto_raise"))
                                set_n = res_n.scalar_one_or_none()
                                notify_enabled = set_n.value.lower() == "true" if set_n else True
                            if notify_enabled:
                                from tg_bot.bot import send_admin_notification
                                raised_str = ", ".join(raised)
                                await send_admin_notification(f"🚀 **Авто-поднятие лотов Starvell:**\nУспешно подняты предложения в категориях: `{raised_str}`")
                        if cooldowns:
                            logger.info(f"[AutoRaiseService] ℹ️ Кулдаун для категорий: {cooldowns}")
                    elif isinstance(result, list) and result:
                        logger.info(f"[AutoRaiseService] Raised lots: {result}")
            except Exception as e:
                logger.error(f"[AutoRaiseService] Error in auto raise loop: {e}")

            await asyncio.sleep(self.interval_seconds)
