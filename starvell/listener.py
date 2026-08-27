import asyncio
from typing import Callable, List, Set, Dict, Any, Awaitable
from core.logger import logger
from starvell.client import StarvellClient
from starvell.models import StarvellEvent, StarvellMessage, StarvellOrder

EventHandler = Callable[[StarvellEvent], Awaitable[None]]

class StarvellListener:
    """
    Background event listener for Starvell.
    Monitors new chat messages and new orders / status updates.
    """
    def __init__(self, client: StarvellClient, poll_interval: float = 3.0):
        self.client = client
        self.poll_interval = poll_interval
        self.handlers: List[EventHandler] = []
        self._is_running = False
        self._task: Optional[asyncio.Task] = None
        
        # Deduplication sets
        self._seen_messages: Set[str] = set()
        self._seen_orders: Dict[str, str] = {}  # order_id -> last_known_status
        self._messages_initialized = False
        self._orders_initialized = False

    def register_handler(self, handler: EventHandler):
        self.handlers.append(handler)

    async def _emit(self, event: StarvellEvent):
        for handler in self.handlers:
            try:
                await handler(event)
            except Exception as e:
                logger.error(f"[StarvellListener] Exception in event handler: {e}")

    async def start(self):
        if self._is_running:
            return
        self._is_running = True
        self._task = asyncio.create_task(self._listen_loop())
        logger.info("[StarvellListener] Event listener started.")

    async def stop(self):
        self._is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("[StarvellListener] Event listener stopped.")

    async def _listen_loop(self):
        while self._is_running:
            try:
                if not self.client.is_simulation:
                    await self._check_orders()
                    await self._check_messages()
            except Exception as e:
                logger.error(f"[StarvellListener] Error in listen loop: {e}")

            await asyncio.sleep(self.poll_interval)

    async def _check_orders(self):
        try:
            orders = await self.client.get_orders()
            if not isinstance(orders, list):
                return

            for order in orders:
                last_status = self._seen_orders.get(order.id)
                status_str = str(order.status).lower() if order.status else "unknown"

                if last_status != status_str:
                    self._seen_orders[order.id] = status_str

                    if not self._orders_initialized:
                        continue

                    event_type = f"order_{status_str}"
                    event = StarvellEvent(
                        event_type=event_type,
                        chat_id=order.chat_id or order.buyer_id,
                        order=order
                    )
                    logger.info(f"[StarvellListener] Order event detected: {order.id} -> {status_str}")
                    await self._emit(event)

            self._orders_initialized = True
        except Exception as e:
            logger.error(f"[StarvellListener] Error checking orders: {e}")

    def is_my_message(self, last_msg: dict) -> bool:
        """
        Comprehensive check to determine if a message was sent by our own account (seller / bot).
        Checks boolean flags, author IDs, public IDs, and participant roles.
        """
        if not isinstance(last_msg, dict):
            return False

        # 1. Direct boolean flags from API/Frontend JSON
        for flag in ("isMyMessage", "isMine", "isOwn", "isSelf", "isMe", "isOutgoing", "isFromMe", "sentByMe"):
            val = last_msg.get(flag)
            if val is True or (isinstance(val, str) and val.lower() == "true"):
                return True

        # 2. Check author object and fields
        author_id = str(last_msg.get("authorId") or last_msg.get("sender_id") or last_msg.get("senderId") or "")
        author_obj = last_msg.get("author") if isinstance(last_msg.get("author"), dict) else {}
        author_pub = str(last_msg.get("authorPublicId") or author_obj.get("publicId") or "")
        author_num = str(author_obj.get("id") or "")

        my_user_id = str(getattr(self.client, 'user_id', '') or '')
        my_public_id = str(getattr(self.client, 'public_id', '') or '')

        if my_user_id and my_user_id.lower() != "none":
            if author_id == my_user_id or author_num == my_user_id:
                return True
        if my_public_id and my_public_id.lower() != "none":
            if author_pub == my_public_id or author_id == my_public_id:
                return True

        # 3. Check author role if present (e.g. "seller", "owner", "me")
        author_role = str(last_msg.get("role") or author_obj.get("role") or "").lower()
        if author_role in ("seller", "owner", "me"):
            return True

        return False

    async def _check_messages(self):
        try:
            # Ensure profile user IDs are loaded if available
            if not self.client.user_id and not self.client.public_id and not self.client.is_simulation:
                try:
                    await self.client.get_profile()
                except Exception:
                    pass

            chats = await self.client.get_chats()
            if not isinstance(chats, list):
                return

            my_public_id = str(self.client.public_id or "")
            my_user_id = str(getattr(self.client, 'user_id', '') or '')

            for chat in chats:
                if not isinstance(chat, dict):
                    continue
                chat_id = str(chat.get("id", ""))
                last_msg = chat.get("lastMessage")
                if not last_msg or not isinstance(last_msg, dict):
                    continue

                msg_id = str(last_msg.get("id", ""))
                if not msg_id:
                    continue

                if msg_id in self._seen_messages:
                    continue

                # Seed existing message IDs on initial run
                if not self._messages_initialized:
                    self._seen_messages.add(msg_id)
                    continue

                self._seen_messages.add(msg_id)

                # Skip messages sent by our own account (seller / bot)
                if self.is_my_message(last_msg):
                    logger.info(f"[StarvellListener] Сообщение от нашего аккаунта в чате {chat_id}. Пропускаем уведомление TG.")
                    event = StarvellEvent(event_type="self_message", chat_id=chat_id)
                    await self._emit(event)
                    continue

                author_id = str(last_msg.get("authorId", last_msg.get("sender_id", "")))
                sender_name = "Покупатель"
                participants = chat.get("participants", [])
                if isinstance(participants, list):
                    for p in participants:
                        if isinstance(p, dict):
                            p_pub = str(p.get("publicId", ""))
                            p_id = str(p.get("id", ""))
                            if (not my_public_id or p_pub != my_public_id) and (not my_user_id or p_id != my_user_id):
                                sender_name = p.get("username", "Покупатель")
                                break

                text_content = last_msg.get("content") or last_msg.get("text") or ""
                if not text_content:
                    continue

                msg_obj = StarvellMessage(
                    id=msg_id,
                    chat_id=chat_id,
                    sender_id=author_id,
                    sender_name=sender_name,
                    text=text_content
                )

                event = StarvellEvent(
                    event_type="new_message",
                    chat_id=chat_id,
                    message=msg_obj
                )
                logger.info(f"[StarvellListener] Новое сообщение в чате {chat_id} от {sender_name}: {text_content[:30]}")
                await self._emit(event)

            self._messages_initialized = True
        except Exception as e:
            logger.error(f"[StarvellListener] Error checking messages: {e}")
