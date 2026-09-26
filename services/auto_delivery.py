import html
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
            if order_record and order_record.status in ("delivered", "completed"):
                logger.info(f"[AutoDelivery] Order {order.id} already delivered. Skipping.")
                return False

            # An order may contain several units; never deliver only the first key.
            quantity = max(1, int(order.amount or 1))
            res = await session.execute(
                select(StockItem).where(
                    StockItem.lot_id == str(order.lot_id),
                    StockItem.is_used == False
                ).order_by(StockItem.id).limit(quantity)
            )
            stock_items = res.scalars().all()

            delivered_text = ""
            if len(stock_items) == quantity:
                for stock_item in stock_items:
                    stock_item.is_used = True
                    stock_item.used_at = datetime.utcnow()
                    stock_item.order_id = str(order.id)
                    stock_item.buyer_id = str(order.buyer_id)
                delivered_text = "\n\n".join(item.item_data for item in stock_items)
                # Reserve the item in this transaction. Roll it back if chat delivery fails.
                await session.flush()
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
                    logger.warning(f"[AutoDelivery] Insufficient stock ({len(stock_items)}/{quantity}) and no template for lot {order.lot_id}, order {order.id}")
                    if self.telegram_notifier:
                        await self.telegram_notifier(
                            f"⚠️ <b>ВНИМАНИЕ! Закончился товар!</b>\n"
                            f"Заказ <code>#{html.escape(str(order.id))}</code> на лот "
                            f"<b>{html.escape(str(order.lot_title))}</b> не может быть выдан автоматически: недостаточно товара ({len(stock_items)}/{quantity})."
                        )
                    return False

            # Send delivered content to Starvell Chat
            header_message = f"✅ **Ваш заказ #{order.id} оплачен и автоматически выдан!**\n\n"
            full_delivery_message = f"{header_message}{delivered_text}\n\nСпасибо за покупку! Оставьте, пожалуйста, отзыв!"

            chat_id = order.chat_id or order.buyer_id
            if not chat_id:
                logger.error(f"[AutoDelivery] No chat or buyer ID for order {order.id}")
                await session.rollback()
                return False
            try:
                sent_ok = await self.client.send_message(chat_id, full_delivery_message, is_auto=True)
            except Exception as e:
                logger.error(f"[AutoDelivery] Failed to send order {order.id}: {e}")
                await session.rollback()
                return False
            if not sent_ok:
                logger.error(f"[AutoDelivery] Chat delivery failed for order {order.id}; stock remains available.")
                await session.rollback()
                return False

            # Record in OrderHistory
            order_price = float(order.total_price or order.price or 0.0)
            if not order_record:
                order_record = OrderHistory(
                    order_id=str(order.id),
                    order_uuid=order.full_id,
                    chat_id=str(chat_id or ""),
                    buyer_id=str(order.buyer_id),
                    buyer_name=order.buyer_name,
                    lot_id=str(order.lot_id),
                    lot_title=order.lot_title,
                    price=order_price,
                    status="delivered",
                    delivered_content=delivered_text
                )
                session.add(order_record)
            else:
                order_record.status = "delivered"
                order_record.delivered_content = delivered_text
                if order.full_id and not order_record.order_uuid:
                    order_record.order_uuid = order.full_id
                if chat_id and not order_record.chat_id:
                    order_record.chat_id = str(chat_id)

            await session.commit()
            if len(stock_items) == quantity:
                logger.info(f"[AutoDelivery] {quantity} stock item(s) used for order {order.id}")

            # Notify Admin in Telegram
            async with AsyncSessionLocal() as db_session:
                res_n = await db_session.execute(select(BotSetting).where(BotSetting.key == "notify_order_delivery"))
                set_n = res_n.scalar_one_or_none()
                notify_enabled = set_n.value.lower() == "true" if set_n else True

            if self.telegram_notifier and notify_enabled:
                await self.telegram_notifier(
                    f"🎉 <b>Автовыдача завершена!</b>\n"
                    f"📦 <b>Заказ:</b> <code>{html.escape(str(order.id))}</code>\n"
                    f"👤 <b>Покупатель:</b> {html.escape(str(order.buyer_name))}\n"
                    f"💵 <b>Сумма:</b> {order_price:.2f} RUB\n"
                    f"🛒 <b>Лот:</b> {html.escape(str(order.lot_title))}"
                )

            return sent_ok
