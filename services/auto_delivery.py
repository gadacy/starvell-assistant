from datetime import datetime
from typing import Optional, Callable, Awaitable
from sqlalchemy import select, update
from core.database.base import AsyncSessionLocal
from core.database.models import StockItem, OrderHistory, BotSetting, AutoResponse
from core.logger import logger
from starvell.client import StarvellClient
from starvell.models import StarvellOrder

class AutoDeliveryService:
    def __init__(self, client: StarvellClient, telegram_notifier: Optional[Callable[[str], Awaitable[None]]] = None):
        self.client = client
        self.telegram_notifier = telegram_notifier

    async def is_enabled(self) -> bool:
        async with AsyncSessionLocal() as session:
            res = await session.execute(
                select(BotSetting).where(BotSetting.key == "auto_delivery_enabled")
            )
            setting = res.scalar_one_or_none()
            if setting and setting.value.lower() == "false":
                return False
            return True

    async def process_order(self, order: StarvellOrder) -> bool:
        if not await self.is_enabled():
            logger.info(f"[AutoDelivery] Auto-delivery is disabled. Skipping order {order.id}")
            return False

        if order.status != "paid":
            return False

        async with AsyncSessionLocal() as session:
            # Check if order already delivered
            existing = await session.execute(
                select(OrderHistory).where(OrderHistory.order_id == str(order.id))
            )
            order_record = existing.scalar_one_or_none()
            if order_record and order_record.status == "delivered":
                logger.info(f"[AutoDelivery] Order {order.id} already delivered. Skipping.")
                return False

            # Search for available line item stock
            res = await session.execute(
                select(StockItem).where(
                    StockItem.lot_id == str(order.lot_id),
                    StockItem.is_used == False
                ).limit(1)
            )
            stock_item = res.scalar_one_or_none()

            delivered_text = ""
            if stock_item:
                stock_item.is_used = True
                stock_item.used_at = datetime.utcnow()
                stock_item.order_id = str(order.id)
                stock_item.buyer_id = str(order.buyer_id)
                delivered_text = stock_item.item_data
                await session.commit()
                logger.info(f"[AutoDelivery] Stock item #{stock_item.id} used for order {order.id}")
            else:
                # Check for template text rule in AutoResponse
                resp_res = await session.execute(
                    select(AutoResponse).where(
                        AutoResponse.trigger_type == "order_paid",
                        AutoResponse.lot_id == str(order.lot_id),
                        AutoResponse.is_active == True
                    )
                )
                template_rule = resp_res.scalar_one_or_none()
                if template_rule:
                    delivered_text = template_rule.response_text
                else:
                    logger.warning(f"[AutoDelivery] NO STOCK AND NO TEMPLATE FOR LOT {order.lot_id}! Order {order.id}")
                    if self.telegram_notifier:
                        await self.telegram_notifier(
                            f"⚠️ **ВНИМАНИЕ! Закончился товар!**\n"
                            f"Заказ `#${order.id}` на лот **{order.lot_title}** не может быть выдан авто-выдачей, так как запасы пустые!"
                        )
                    return False

            # Send delivered content to Starvell Chat
            header_message = f"✅ **Ваш заказ #{order.id} оплачен и автоматически выдан!**\n\n"
            full_delivery_message = f"{header_message}{delivered_text}\n\nСпасибо за покупку! Оставьте, пожалуйста, отзыв!"

            chat_id = order.chat_id or order.buyer_id
            sent_ok = await self.client.send_message(chat_id, full_delivery_message, is_auto=True)

            # Record in OrderHistory
            if not order_record:
                order_record = OrderHistory(
                    order_id=str(order.id),
                    buyer_id=str(order.buyer_id),
                    buyer_name=order.buyer_name,
                    lot_id=str(order.lot_id),
                    lot_title=order.lot_title,
                    price=order.total_price or order.price,
                    status="delivered",
                    delivered_content=delivered_text
                )
                session.add(order_record)
            else:
                order_record.status = "delivered"
                order_record.delivered_content = delivered_text

            await session.commit()

            # Notify Admin in Telegram
            async with AsyncSessionLocal() as db_session:
                res_n = await db_session.execute(select(BotSetting).where(BotSetting.key == "notify_order_delivery"))
                set_n = res_n.scalar_one_or_none()
                notify_enabled = set_n.value.lower() == "true" if set_n else True

            if self.telegram_notifier and notify_enabled:
                await self.telegram_notifier(
                    f"🎉 **Автовыдача завершена!**\n"
                    f"📦 **Заказ:** `{order.id}`\n"
                    f"👤 **Покупатель:** {order.buyer_name}\n"
                    f"💵 **Сумма:** {order.total_price:.2f} RUB\n"
                    f"🛒 **Лот:** {order.lot_title}"
                )

            return sent_ok
