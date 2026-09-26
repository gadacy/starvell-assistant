import unittest
from contextlib import ExitStack
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message, User
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from core.database.base import Base
from core.database.models import AutoResponse, BotSetting, SeenChat
from services.auto_responder import AutoResponderService
from services.chat_relay import ChatRelayService
from services.chat_state import get_reply_target, has_purchase, record_purchase, save_reply_target
from starvell.listener import StarvellListener
from starvell.models import StarvellMessage, StarvellOrder
from tg_bot.handlers import chat as chat_handler
from tg_bot.middlewares import AdminAuthMiddleware, ChatNavigationMiddleware


class ChatFlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.patches = ExitStack()
        for module in ("services.chat_state", "services.chat_relay", "services.auto_responder", "starvell.listener"):
            self.patches.enter_context(patch(f"{module}.AsyncSessionLocal", self.sessions))
        self.patches.enter_context(patch("services.chat_relay.config.telegram_admin_ids", [101, 202]))
        self.client = MagicMock()
        self.client.user_id = "seller"
        self.client.public_id = "seller-public"
        self.client.is_simulation = False
        self.client.get_chats = AsyncMock(return_value=[])
        self.client.get_chat_events = AsyncMock(return_value=[])
        self.client.get_orders = AsyncMock(return_value=[])
        self.client.send_message = AsyncMock(return_value=True)
        self.bot = MagicMock()
        self.bot.send_message = AsyncMock(side_effect=lambda chat_id, *a, **kw: SimpleNamespace(
            chat=SimpleNamespace(id=chat_id), message_id=500
        ))
        self.patches.enter_context(patch("services.chat_relay.get_bot", return_value=self.bot))
        self.patches.enter_context(patch("tg_bot.handlers.features.get_client", return_value=self.client))
        self.message = StarvellMessage(id="m1", chat_id="chat-A", sender_id="buyer-A", sender_name="Alice", text="hello")
        self.storage = MemoryStorage()
        self.state = FSMContext(self.storage, StorageKey(bot_id=1, chat_id=101, user_id=101))

    async def asyncTearDown(self):
        self.patches.close()
        await self.storage.close()
        await self.engine.dispose()

    def telegram_message(self, text="answer", reply_id=None, chat_id=101):
        msg = MagicMock(spec=Message)
        msg.text = text
        msg.caption = None
        msg.chat = SimpleNamespace(id=chat_id)
        msg.from_user = MagicMock(spec=User)
        msg.from_user.id = chat_id
        msg.reply_to_message = SimpleNamespace(message_id=reply_id) if reply_id else None
        msg.answer = AsyncMock(return_value=SimpleNamespace(chat=msg.chat, message_id=600))
        return msg

    async def dispatch(self, message):
        return await chat_handler.router.propagate_event(
            update_type="message", event=message, state=self.state,
            raw_state=await self.state.get_state(), bot=self.bot,
        )

    async def test_purchase_suppresses_greeting_and_rules_after_restart_and_cooldown(self):
        async with self.sessions() as session:
            session.add_all([
                BotSetting(key="auto_greeting_mode", value="cooldown"),
                BotSetting(key="auto_greeting_cooldown_hours", value="1"),
                AutoResponse(title="Greeting", trigger_type="contains", pattern="hello", response_text="Welcome"),
                SeenChat(chat_id="chat-A", last_seen_at=datetime.utcnow() - timedelta(days=30)),
            ])
            await session.commit()
        await record_purchase("order-A", "chat-A", "buyer-A")
        # Fresh service instances only know what was persisted, not the purchase event.
        relay = ChatRelayService(self.client)
        await relay.init_seen_chats()
        await relay.process_incoming_message(self.message)
        self.assertFalse(await AutoResponderService(self.client).process_message(self.message))
        self.client.send_message.assert_not_awaited()
        self.assertEqual(self.bot.send_message.await_count, 2)

    async def test_new_buyer_still_receives_greeting(self):
        await ChatRelayService(self.client).process_incoming_message(self.message)
        self.client.send_message.assert_awaited_once()
        self.assertIn("Alice", self.client.send_message.call_args.args[1])

    async def test_purchase_without_chat_is_matched_by_buyer(self):
        await record_purchase("order-A", buyer_id="buyer-A")
        await ChatRelayService(self.client).process_incoming_message(self.message)
        self.client.send_message.assert_not_awaited()

    async def test_startup_orders_are_recorded_without_notifications(self):
        self.client.get_orders.return_value = [StarvellOrder(
            id="order-A", chat_id="chat-A", buyer_id="buyer-A", buyer_name="Alice",
            lot_id="lot-A", lot_title="Key", status="paid",
        )]
        listener = StarvellListener(self.client)
        handler = AsyncMock()
        listener.register_handler(handler)
        await listener._check_orders()
        self.assertTrue(await has_purchase("chat-A"))
        handler.assert_not_awaited()

    async def test_history_finds_purchase_hidden_by_newer_messages(self):
        purchase = {"id": "purchase", "type": "NOTIFICATION", "createdAt": "2026-01-01T10:00:00",
                    "metadata": {"notificationType": "ORDER_PAID", "orderId": "order-A"}}
        first = {"id": "first", "authorId": "buyer-A", "content": "hello", "createdAt": "2026-01-01T10:00:01"}
        last = {"id": "last", "authorId": "buyer-A", "content": "anyone here?", "createdAt": "2026-01-01T10:00:02"}
        self.client.get_chats.return_value = [{"id": "chat-A", "lastMessage": last}]
        self.client.get_chat_events.return_value = [last, first, purchase]
        listener = StarvellListener(self.client)
        listener._messages_initialized = True
        messages = []
        relay = ChatRelayService(self.client)
        async def handle(event):
            if event.message:
                messages.append(event.message.text)
                await relay.process_incoming_message(event.message)
        listener.register_handler(handle)
        await listener._check_messages()
        self.assertEqual(messages, ["hello", "anyone here?"])
        self.client.send_message.assert_not_awaited()
        await listener._check_messages()
        self.assertEqual(len(messages), 2)

    async def test_forwarded_messages_store_independent_admin_reply_targets(self):
        await record_purchase("order-A", "chat-A")
        await ChatRelayService(self.client).process_incoming_message(self.message)
        self.assertEqual(await get_reply_target(101, 500), "chat-A")
        self.assertEqual(await get_reply_target(202, 500), "chat-A")
        self.assertIsNone(await get_reply_target(303, 500))

    async def test_explicit_reply_overrides_active_chat(self):
        await save_reply_target(101, 500, "chat-A")
        await self.state.set_state(chat_handler.ChatReplyState.active)
        await self.state.update_data(starvell_chat_id="chat-B")
        await self.dispatch(self.telegram_message(reply_id=500))
        self.client.send_message.assert_awaited_once_with("chat-A", "answer")
        self.assertEqual(await get_reply_target(101, 600), "chat-A")
        self.assertIsNone(await self.state.get_state())

    async def test_reply_button_opens_chat_and_maps_prompt(self):
        call = MagicMock(spec=CallbackQuery)
        call.data = "reply_chat_chat-A"
        call.answer = AsyncMock()
        call.message = self.telegram_message()
        await chat_handler.open_chat(call, self.state)
        self.assertEqual((await self.state.get_data())["starvell_chat_id"], "chat-A")
        self.assertEqual(await get_reply_target(101, 600), "chat-A")
        await self.dispatch(self.telegram_message("from button"))
        self.client.send_message.assert_awaited_once_with("chat-A", "from button")

    async def test_menu_navigation_closes_active_chat(self):
        await self.state.set_state(chat_handler.ChatReplyState.active)
        await self.state.update_data(starvell_chat_id="chat-A")
        call = MagicMock(spec=CallbackQuery)
        call.data = "menu_settings"
        handler = AsyncMock()
        await ChatNavigationMiddleware()(handler, call, {"state": self.state})
        self.assertIsNone(await self.state.get_state())
        handler.assert_awaited_once()
        await self.dispatch(self.telegram_message("not a buyer message"))
        self.client.send_message.assert_not_awaited()

    async def test_reply_mapping_is_scoped_to_telegram_chat(self):
        await save_reply_target(101, 500, "chat-A")
        await save_reply_target(202, 500, "chat-B")
        await self.dispatch(self.telegram_message(reply_id=500, chat_id=202))
        self.client.send_message.assert_awaited_once_with("chat-B", "answer")

    async def test_active_chat_accepts_multiple_messages_and_keeps_state_on_failure(self):
        await self.state.set_state(chat_handler.ChatReplyState.active)
        await self.state.update_data(starvell_chat_id="chat-A")
        self.client.send_message.side_effect = [True, False, True]
        for text in ("first", "second", "third"):
            await self.dispatch(self.telegram_message(text))
        self.assertEqual(self.client.send_message.await_count, 3)
        self.assertEqual(await self.state.get_state(), chat_handler.ChatReplyState.active.state)

    async def test_unknown_reply_and_media_are_not_sent_to_active_buyer(self):
        await self.state.set_state(chat_handler.ChatReplyState.active)
        await self.state.update_data(starvell_chat_id="chat-A")
        await self.dispatch(self.telegram_message(reply_id=999))
        media = self.telegram_message(text=None)
        await self.dispatch(media)
        self.client.send_message.assert_not_awaited()
        media.answer.assert_awaited_once()

    async def test_cancel_closes_chat_and_commands_are_not_sent(self):
        await self.state.set_state(chat_handler.ChatReplyState.active)
        await self.state.update_data(starvell_chat_id="chat-A")
        await self.dispatch(self.telegram_message("/cancel"))
        self.assertIsNone(await self.state.get_state())
        self.client.send_message.assert_not_awaited()

    async def test_unauthorized_reply_is_blocked(self):
        await save_reply_target(303, 500, "chat-A")
        msg = self.telegram_message(reply_id=500, chat_id=303)
        handler = AsyncMock(side_effect=lambda event, data: self.dispatch(event))
        await AdminAuthMiddleware()(handler, msg, {})
        handler.assert_not_awaited()
        self.client.send_message.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
