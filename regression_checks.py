import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from aiogram.types import Message, User

from core.database.base import Base
from core.database.models import OrderHistory, StockItem
from services.auto_delivery import AutoDeliveryService
from starvell.client import StarvellClient
from starvell.listener import StarvellListener
from starvell.models import StarvellOrder
from tg_bot.middlewares import AdminAuthMiddleware


class DeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.sessions() as session:
            session.add_all([
                StockItem(lot_id="lot-1", item_data="key-1"),
                StockItem(lot_id="lot-1", item_data="key-2"),
            ])
            await session.commit()
        self.order = StarvellOrder(
            id="order-1", buyer_id="buyer-1", buyer_name="Buyer", chat_id="chat-1",
            lot_id="lot-1", lot_title="Lot", amount=2, status="paid"
        )

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_failed_send_does_not_consume_stock_or_mark_delivered(self):
        client = MagicMock()
        client.send_message = AsyncMock(side_effect=[False, True])
        service = AutoDeliveryService(client)
        with patch("services.auto_delivery.AsyncSessionLocal", self.sessions):
            self.assertFalse(await service.process_order(self.order))
            async with self.sessions() as session:
                items = (await session.execute(select(StockItem))).scalars().all()
                self.assertTrue(all(not item.is_used for item in items))
                self.assertIsNone((await session.execute(select(OrderHistory))).scalar_one_or_none())

            self.assertTrue(await service.process_order(self.order))
            async with self.sessions() as session:
                items = (await session.execute(select(StockItem))).scalars().all()
                self.assertTrue(all(item.is_used for item in items))
                record = (await session.execute(select(OrderHistory))).scalar_one()
                self.assertIn("key-1", record.delivered_content)
                self.assertIn("key-2", record.delivered_content)

            self.assertFalse(await service.process_order(self.order))
            self.assertEqual(client.send_message.await_count, 2)


class EventAndSecurityTests(unittest.IsolatedAsyncioTestCase):
    async def test_notification_without_order_object_is_processed(self):
        client = MagicMock()
        client.user_id = "seller"
        client.public_id = None
        client.is_simulation = False
        client.get_chat_events = AsyncMock(return_value=[])
        client.get_chats = AsyncMock(return_value=[{
            "id": "chat-1", "lastMessage": {
                "id": "msg-1", "type": "NOTIFICATION",
                "metadata": {"notificationType": "ORDER_PAID", "orderShortId": "order-1"},
            }
        }])
        listener = StarvellListener(client)
        listener._messages_initialized = True
        events = []
        listener.register_handler(lambda event: _append_event(events, event))
        with patch("starvell.listener.record_chat_purchase", new_callable=AsyncMock):
            await listener._check_messages()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].order.id, "order-1")

    async def test_empty_admin_list_denies_access(self):
        event = MagicMock(spec=Message)
        event.from_user = MagicMock(spec=User)
        event.from_user.id = 123
        event.answer = AsyncMock()
        handler = AsyncMock()
        with patch("tg_bot.middlewares.config.telegram_admin_ids", []):
            result = await AdminAuthMiddleware()(handler, event, {})
        self.assertIsNone(result)
        handler.assert_not_awaited()
        event.answer.assert_awaited_once()

    async def test_client_reports_failed_http_sends(self):
        client = StarvellClient(api_key="test-token")
        response = MagicMock(status_code=403)
        http_client = MagicMock()
        http_client.post = AsyncMock(return_value=response)
        client.get_client = AsyncMock(return_value=http_client)
        self.assertFalse(await client.send_message("chat-1", "hello"))
        self.assertEqual(http_client.post.await_count, 3)


async def _append_event(events, event):
    events.append(event)


if __name__ == "__main__":
    unittest.main()
