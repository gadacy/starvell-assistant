from sqlalchemy import or_, select

from core.database.base import AsyncSessionLocal
from core.database.models import ChatPurchase, OrderHistory, TelegramChatLink


async def record_purchase(order_id: str, chat_id: str = None, buyer_id: str = None):
    if not order_id or not (chat_id or buyer_id):
        return
    async with AsyncSessionLocal() as session:
        record = await session.get(ChatPurchase, str(order_id))
        if record is None:
            record = ChatPurchase(order_id=str(order_id))
            session.add(record)
        if chat_id:
            record.chat_id = str(chat_id)
        if buyer_id:
            record.buyer_id = str(buyer_id)
        await session.commit()


async def record_order_purchase(order):
    if str(order.status).lower() in {"paid", "delivered", "completed", "refunded"}:
        await record_purchase(order.id, order.chat_id, order.buyer_id)


async def record_chat_purchase(chat: dict):
    """Capture order context even when a later text message hides the purchase event."""
    last = chat.get("lastMessage")
    last = last if isinstance(last, dict) else {}
    order = last.get("order") or chat.get("order")
    order = order if isinstance(order, dict) else {}
    metadata = last.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    order_id = order.get("shortId") or order.get("id") or metadata.get("orderShortId") or metadata.get("orderId")
    if not order_id:
        return
    # An associated order suppresses greetings; this does not authorize delivery.
    buyer = last.get("buyer")
    buyer = buyer if isinstance(buyer, dict) else {}
    await record_purchase(order_id, chat.get("id"), order.get("buyerId") or buyer.get("id"))


async def has_purchase(chat_id: str, buyer_id: str = None) -> bool:
    async with AsyncSessionLocal() as session:
        for model in (ChatPurchase, OrderHistory):
            conditions = []
            if chat_id:
                conditions.append(model.chat_id == str(chat_id))
            if buyer_id:
                conditions.append(model.buyer_id == str(buyer_id))
            if not conditions:
                continue
            query = select(model.order_id).where(or_(*conditions))
            if model is OrderHistory:
                query = query.where(model.status.in_(["paid", "delivered", "completed", "refunded"]))
            if (await session.execute(query.limit(1))).first():
                return True
    return False


async def save_reply_target(telegram_chat_id: int, message_id: int, starvell_chat_id: str):
    if not starvell_chat_id:
        return
    async with AsyncSessionLocal() as session:
        await session.merge(TelegramChatLink(
            telegram_chat_id=telegram_chat_id,
            telegram_message_id=message_id,
            starvell_chat_id=str(starvell_chat_id),
        ))
        await session.commit()


async def get_reply_target(telegram_chat_id: int, message_id: int):
    async with AsyncSessionLocal() as session:
        link = await session.get(TelegramChatLink, (telegram_chat_id, message_id))
        return link.starvell_chat_id if link else None
