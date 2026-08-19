import re
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import select
from core.database.base import AsyncSessionLocal
from core.database.models import AutoResponse, StockItem, BotSetting
from core.logger import logger
from starvell.client import StarvellClient
from starvell.models import StarvellEvent, StarvellMessage, StarvellOrder

class AutoResponderService:
    def __init__(self, client: StarvellClient):
        self.client = client

    async def is_enabled(self) -> bool:
        async with AsyncSessionLocal() as session:
            res = await session.execute(
                select(BotSetting).where(BotSetting.key == "auto_responder_enabled")
            )
            setting = res.scalar_one_or_none()
            if setting and setting.value.lower() == "false":
                return False
            return True

    async def process_message(self, message: StarvellMessage, order: Optional[StarvellOrder] = None) -> bool:
        if not await self.is_enabled():
            return False

        text = message.text.strip()
        if not text:
            return False

        async with AsyncSessionLocal() as session:
            res = await session.execute(
                select(AutoResponse).where(AutoResponse.is_active == True)
            )
            rules = res.scalars().all()

        for rule in rules:
            if rule.lot_id and order and str(order.lot_id) != str(rule.lot_id):
                continue

            matched = False
            if rule.trigger_type == "exact" and text.lower() == rule.pattern.lower():
                matched = True
            elif rule.trigger_type == "contains" and rule.pattern.lower() in text.lower():
                matched = True
            elif rule.trigger_type == "regex":
                try:
                    if re.search(rule.pattern, text, re.IGNORECASE):
                        matched = True
                except Exception as e:
                    logger.error(f"[AutoResponder] Regex error in rule {rule.id}: {e}")

            if matched:
                response_text = await self._format_text(rule.response_text, message, order)
                logger.info(f"[AutoResponder] Matched rule '{rule.title}'. Sending reply to chat {message.chat_id}")
                await self.client.send_message(message.chat_id, response_text, is_auto=True)
                return True

        return False

    async def _format_text(self, text: str, message: StarvellMessage, order: Optional[StarvellOrder] = None) -> str:
        now = datetime.now()
        stock_count = "0"
        
        lot_id = order.lot_id if order else None
        if lot_id:
            async with AsyncSessionLocal() as session:
                res = await session.execute(
                    select(StockItem).where(
                        StockItem.lot_id == str(lot_id),
                        StockItem.is_used == False
                    )
                )
                items = res.scalars().all()
                stock_count = str(len(items))

        replacements = {
            "{buyer_name}": message.sender_name or "Покупатель",
            "{buyer_id}": message.sender_id or "",
            "{order_id}": order.id if order else "—",
            "{lot_name}": order.lot_title if order else "—",
            "{price}": f"{order.price:.2f}" if order else "—",
            "{time}": now.strftime("%H:%M:%S"),
            "{date}": now.strftime("%Y-%m-%d"),
            "{stock_count}": stock_count
        }

        result = text
        for key, val in replacements.items():
            result = result.replace(key, val)

        return result
