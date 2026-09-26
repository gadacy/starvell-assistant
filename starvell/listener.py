import asyncio
from typing import Callable, List, Set, Dict, Any, Awaitable, Optional
from sqlalchemy import select
from core.database.base import AsyncSessionLocal
from core.database.models import OrderHistory, ReviewHistory
from core.logger import logger
from starvell.client import StarvellClient
from starvell.models import StarvellEvent, StarvellMessage, StarvellOrder, StarvellReview
from services.chat_state import record_order_purchase, record_chat_purchase

EventHandler = Callable[[StarvellEvent], Awaitable[None]]

class StarvellListener:
    """
    Background event listener for Starvell.
    Monitors new chat messages, notification events, new orders, and new reviews.
    """
    def __init__(self, client: StarvellClient, poll_interval: float = 3.0):
        self.client = client
        self.poll_interval = poll_interval
        self.handlers: List[EventHandler] = []
        self._is_running = False
        self._task: Optional[asyncio.Task] = None
        
        # Deduplication sets
        self._seen_messages: Set[str] = set()
        self._chat_last_messages: Dict[str, str] = {}
        self._seen_orders: Dict[str, str] = {}  # order_id -> last_known_status
        self._seen_reviews: Set[str] = set()
        self._messages_initialized = False
        self._orders_initialized = False
        self._reviews_initialized = False

    def register_handler(self, handler: EventHandler):
        self.handlers.append(handler)

    async def _emit(self, event: StarvellEvent):
        for handler in self.handlers:
            try:
                await handler(event)
            except Exception as e:
                logger.error(f"[StarvellListener] Exception in event handler: {e}")

    async def init_seen_state(self):
        """Pre-seed seen orders and reviews from database to prevent re-alerting on bot startup."""
        try:
            async with AsyncSessionLocal() as session:
                res = await session.execute(select(OrderHistory))
                orders_db = res.scalars().all()
                for o in orders_db:
                    if o.order_id:
                        self._seen_orders[str(o.order_id)] = str(o.status or "completed").lower()

                res_rev = await session.execute(select(ReviewHistory))
                revs_db = res_rev.scalars().all()
                for r in revs_db:
                    if r.review_id:
                        self._seen_reviews.add(str(r.review_id))

            if self._seen_orders:
                logger.info(f"[StarvellListener] Pre-seeded {len(self._seen_orders)} known orders from database.")
            if self._seen_reviews:
                logger.info(f"[StarvellListener] Pre-seeded {len(self._seen_reviews)} known reviews from database.")
        except Exception as e:
            logger.warning(f"[StarvellListener] Error pre-seeding state from DB: {e}")

    async def start(self):
        if self._is_running:
            return
        self._is_running = True
        await self.init_seen_state()
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
                    await self._check_reviews()
            except Exception as e:
                logger.error(f"[StarvellListener] Error in listen loop: {e}")

            await asyncio.sleep(self.poll_interval)

    async def _check_reviews(self):
        try:
            reviews = await self.client.get_reviews()
            if not isinstance(reviews, list):
                return

            for rev in reviews:
                if not rev.id:
                    continue

                if rev.id not in self._seen_reviews:
                    self._seen_reviews.add(rev.id)

                    # Initial run: seed to DB without firing notifications
                    if not self._reviews_initialized:
                        try:
                            async with AsyncSessionLocal() as session:
                                chk = await session.execute(
                                    select(ReviewHistory).where(ReviewHistory.review_id == str(rev.id))
                                )
                                if not chk.scalar_one_or_none():
                                    session.add(ReviewHistory(
                                        review_id=rev.id,
                                        order_id=rev.order_id,
                                        order_short_id=rev.order_short_id,
                                        rating=rev.rating,
                                        content=rev.content,
                                        author_name=rev.buyer_name,
                                        lot_title=rev.lot_title,
                                        created_at=rev.created_at
                                    ))
                                    await session.commit()
                        except Exception as e:
                            logger.warning(f"[StarvellListener] Error saving initial review {rev.id}: {e}")
                        continue

                    # Save new review to DB
                    try:
                        async with AsyncSessionLocal() as session:
                            chk = await session.execute(
                                select(ReviewHistory).where(ReviewHistory.review_id == str(rev.id))
                            )
                            if not chk.scalar_one_or_none():
                                session.add(ReviewHistory(
                                    review_id=rev.id,
                                    order_id=rev.order_id,
                                    order_short_id=rev.order_short_id,
                                    rating=rev.rating,
                                    content=rev.content,
                                    author_name=rev.buyer_name,
                                    lot_title=rev.lot_title,
                                    created_at=rev.created_at
                                ))
                                await session.commit()
                    except Exception as e:
                        logger.warning(f"[StarvellListener] Error saving review {rev.id} to DB: {e}")

                    event = StarvellEvent(
                        event_type="new_review",
                        chat_id=rev.chat_id,
                        review=rev
                    )
                    logger.info(f"[StarvellListener] New review detected: {rev.rating}⭐ by {rev.buyer_name} for order {rev.order_short_id or rev.order_id}")
                    await self._emit(event)

            self._reviews_initialized = True
        except Exception as e:
            logger.error(f"[StarvellListener] Error checking reviews: {e}")

    async def _check_orders(self):
        try:
            orders = await self.client.get_orders()
            if not isinstance(orders, list):
                return

            for order in orders:
                await record_order_purchase(order)
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
                    logger.info(f"[StarvellListener] Order event detected: {order.id} -> {status_str} ({order.lot_title[:30]})")
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

            # The chat list contains only the last message. Read changed chats so a
            # purchase followed by a buyer's message cannot disappear between polls.
            expanded_chats = []
            for chat in chats:
                if not isinstance(chat, dict):
                    continue
                await record_chat_purchase(chat)
                last = chat.get("lastMessage")
                if not isinstance(last, dict) or str(last.get("id") or "") in self._seen_messages:
                    continue
                history = []
                try:
                    history = await self.client.get_chat_events(str(chat.get("id") or ""))
                except Exception as exc:
                    logger.warning(f"[StarvellListener] Could not load chat history: {exc}")
                if not isinstance(history, list):
                    history = []
                history = [item for item in history if isinstance(item, dict)]
                if not any(str(item.get("id")) == str(last.get("id")) for item in history):
                    history.append(last)
                history.sort(key=lambda item: str(item.get("createdAt") or ""))
                chat_key = str(chat.get("id") or "")
                previous_id = self._chat_last_messages.get(chat_key)
                # Persist purchase context from the whole returned history, but forward
                # only messages after the previous cursor when it is still available.
                for item in history:
                    await record_chat_purchase(dict(chat, lastMessage=item))
                if previous_id:
                    previous_index = next((i for i, item in enumerate(history) if str(item.get("id")) == previous_id), None)
                    if previous_index is not None:
                        history = history[previous_index + 1:]
                self._chat_last_messages[chat_key] = str(last.get("id") or "")
                for item in history:
                    entry = dict(chat, lastMessage=item)
                    expanded_chats.append(entry)

            for chat in expanded_chats:
                if not isinstance(chat, dict):
                    continue
                chat_id = str(chat.get("id", ""))
                last_msg = chat.get("lastMessage")
                if not last_msg or not isinstance(last_msg, dict):
                    continue

                msg_id = str(last_msg.get("id", ""))
                if not msg_id:
                    continue

                msg_type = str(last_msg.get("type") or "").upper()
                meta = last_msg.get("metadata") if isinstance(last_msg.get("metadata"), dict) else {}
                ntype = str(meta.get("notificationType") or "").upper()

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

                # Buyer name extraction
                sender_name = "Покупатель"
                buyer_obj = last_msg.get("buyer") if isinstance(last_msg.get("buyer"), dict) else {}
                if buyer_obj.get("username"):
                    sender_name = buyer_obj.get("username")
                else:
                    participants = chat.get("participants", [])
                    if isinstance(participants, list):
                        for p in participants:
                            if isinstance(p, dict):
                                p_pub = str(p.get("publicId", ""))
                                p_id = str(p.get("id", ""))
                                if (not my_public_id or p_pub != my_public_id) and (not my_user_id or p_id != my_user_id):
                                    sender_name = p.get("username", "Покупатель")
                                    break

                # 1. Handle NOTIFICATION type (order updates, reviews, purchases)
                if msg_type == "NOTIFICATION" or ntype:
                    ord_obj = last_msg.get("order") if isinstance(last_msg.get("order"), dict) else {}
                    order_full_id = str(ord_obj.get("id") or meta.get("orderId") or "")
                    order_short_id = str(ord_obj.get("shortId") or meta.get("orderShortId") or "")
                    order_id = order_short_id or order_full_id
                    
                    if ntype in ["ORDER_CREATED", "ORDER_PAID", "ORDER_NEW", "ORDER_PAYMENT"]:
                        status_str = "paid"
                    elif ntype in ["ORDER_COMPLETED", "ORDER_SELLER_COMPLETED", "ORDER_BUYER_CONFIRMED"]:
                        status_str = "completed"
                    elif ntype in ["ORDER_CANCELLED", "ORDER_REFUNDED"]:
                        status_str = "refunded"
                    elif ntype == "REVIEW_CREATED":
                        status_str = "review"
                        # Trigger review check immediately
                        await self._check_reviews()
                        continue
                    else:
                        # Other site notifications must not trigger auto-delivery.
                        continue

                    if order_id and status_str != "review":
                        last_st = self._seen_orders.get(order_id)
                        if status_str == "paid" and last_st in {"completed", "refunded", "cancelled", "canceled"}:
                            continue
                        if last_st != status_str:
                            self._seen_orders[order_id] = status_str

                            # Lot title & qty
                            try:
                                qty = max(1, int(ord_obj.get("quantity") or 1))
                            except (TypeError, ValueError):
                                qty = 1
                            lot_title = f"Заказ #{order_id}"
                            lot_id = order_id
                            if ord_obj:
                                off = ord_obj.get("offerDetails") if isinstance(ord_obj.get("offerDetails"), dict) else {}
                                descs = off.get("descriptions", {}).get("rus", {}) if isinstance(off.get("descriptions"), dict) else {}
                                lot_title = descs.get("briefDescription") or descs.get("description") or lot_title
                                lot_id = str(ord_obj.get("offerId") or off.get("id") or order_id)

                            order_model = StarvellOrder(
                                id=order_id,
                                short_id=order_short_id or (order_id if len(order_id) < 20 else None),
                                full_id=order_full_id or (order_id if len(order_id) >= 20 else None),
                                buyer_id=str(buyer_obj.get("id") or ""),
                                buyer_name=sender_name,
                                lot_id=lot_id,
                                lot_title=lot_title,
                                amount=qty,
                                price=0.0,
                                total_price=0.0,
                                status=status_str,
                                chat_id=chat_id
                            )
                            event = StarvellEvent(
                                event_type=f"order_{status_str}",
                                chat_id=chat_id,
                                order=order_model
                            )
                            logger.info(f"[StarvellListener] Notification event for order #{order_id} ({status_str}) in chat {chat_id}")
                            await self._emit(event)
                            continue

                    # System notifications must never become buyer text messages.
                    continue

                # 2. Handle standard chat text message
                text_content = last_msg.get("content") or last_msg.get("text") or ""
                if not text_content:
                    continue

                author = last_msg.get("author") if isinstance(last_msg.get("author"), dict) else {}
                author_id = str(last_msg.get("authorId") or last_msg.get("senderId") or last_msg.get("sender_id") or author.get("id") or author.get("publicId") or "")
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
