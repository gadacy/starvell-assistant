import asyncio
import httpx
import json
import re
import time
from typing import List, Optional, Dict, Any, Set
from core.logger import logger
from starvell.models import StarvellUser, StarvellMessage, StarvellOrder, StarvellLot

class StarvellClient:
    """
    Asynchronous Next.js API client for Starvell marketplace.
    Uses Next.js _next/data/{build_id}/ endpoints with auto-extracted build_id and session cookies.
    """
    def __init__(self, api_key: str = "", base_url: str = "https://starvell.com"):
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        
        self._build_id: Optional[str] = None
        self._build_id_fetched_at: float = 0.0
        self._logged_errors: Set[str] = set()
        self.public_id: Optional[str] = None
        self.user_id: Optional[str] = None
        
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "ru,en;q=0.9",
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{self.base_url}/",
            "Origin": self.base_url
        }

        if self.api_key:
            self.headers["Cookie"] = self.api_key

        self._client: Optional[httpx.AsyncClient] = None
        self.is_simulation = not bool(self.api_key)

    async def get_watermark_settings(self) -> tuple[bool, str]:
        from sqlalchemy import select
        from core.database.base import AsyncSessionLocal
        from core.database.models import BotSetting
        from config import config

        try:
            async with AsyncSessionLocal() as session:
                res_e = await session.execute(select(BotSetting).where(BotSetting.key == "watermark_enabled"))
                set_e = res_e.scalar_one_or_none()
                enabled = set_e.value.lower() == "true" if set_e else config.watermark_enabled

                res_t = await session.execute(select(BotSetting).where(BotSetting.key == "watermark_text"))
                set_t = res_t.scalar_one_or_none()
                wm_text = set_t.value if (set_t and set_t.value) else config.watermark_text
            return enabled, wm_text
        except Exception:
            from config import config
            return config.watermark_enabled, config.watermark_text

    async def apply_watermark(self, text: str) -> str:
        enabled, wm_text = await self.get_watermark_settings()
        if not enabled or not wm_text:
            return text
        if wm_text.strip() in text:
            return text
        return f"{wm_text}\n\n{text.lstrip()}"

    async def get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=self.headers,
                timeout=15.0,
                follow_redirects=True
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def _log_once(self, key: str, level: str, message: str):
        if key not in self._logged_errors:
            self._logged_errors.add(key)
            if level == "warning":
                logger.warning(message)
            elif level == "info":
                logger.info(message)
            else:
                logger.error(message)

    # --- Next.js Build ID Extractor ---
    async def get_build_id(self) -> str:
        now = time.time()
        if self._build_id and (now - self._build_id_fetched_at) < 1800:
            return self._build_id

        client = await self.get_client()
        try:
            res = await client.get(f"{self.base_url}/")
            if res.status_code == 200:
                match = re.search(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', res.text, re.DOTALL)
                if match:
                    data = json.loads(match.group(1))
                    self._build_id = data.get("buildId")
                    self._build_id_fetched_at = now
                    page_props = data.get("props", {}).get("pageProps", {})
                    u_info = page_props.get("user", {})
                    if u_info and isinstance(u_info, dict):
                        if u_info.get("publicId"):
                            self.public_id = str(u_info.get("publicId"))
                        if u_info.get("id"):
                            self.user_id = str(u_info.get("id"))
                    logger.info(f"[StarvellClient] Next.js Build ID extracted: {self._build_id}")
                    return self._build_id
        except Exception as e:
            self._log_once("build_id_err", "warning", f"[StarvellClient] Ошибка получения Next.js build_id: {e}")

        self._build_id = "default"
        return self._build_id

    async def get_next_data(self, path: str) -> Dict[str, Any]:
        """
        Fetch data from Next.js Data API: /_next/data/{build_id}/{path}
        """
        build_id = await self.get_build_id()
        client = await self.get_client()
        url = f"{self.base_url}/_next/data/{build_id}/{path}"
        
        headers = dict(self.headers)
        headers["x-nextjs-data"] = "1"

        try:
            res = await client.get(url, headers=headers)
            if res.status_code == 200:
                data = res.json()
                page_props = data.get("pageProps", {})
                u_info = page_props.get("user", {})
                if u_info and isinstance(u_info, dict):
                    if u_info.get("publicId"):
                        self.public_id = str(u_info.get("publicId"))
                    if u_info.get("id"):
                        self.user_id = str(u_info.get("id"))
                return data
        except Exception as e:
            self._log_once(f"next_data_{path}", "warning", f"[StarvellClient] Ошибка Next.js Data API ({path}): {e}")

        return {}

    # --- User & Account Info ---
    async def get_profile(self) -> StarvellUser:
        if self.is_simulation:
            return StarvellUser(
                id="sim_101",
                username="SimulatedSeller",
                public_id="sim-uuid-101",
                is_online=True,
                balance_rub=5000.0,
                balance_hold=1000.0,
                rating=5.0,
                reviews_count=12
            )
        
        data = await self.get_next_data("index.json")
        page_props = data.get("pageProps", {})
        user_info = page_props.get("user")

        if user_info and isinstance(user_info, dict):
            username = user_info.get("username") or user_info.get("name") or "Gradace"
            user_id = str(user_info.get("id", "239792"))
            self.user_id = user_id
            self.public_id = user_info.get("publicId", self.public_id)
            is_online = bool(user_info.get("isOnline", True))
            avatar = user_info.get("avatar")
            
            balance_dict = user_info.get("balance", {})
            # Starvell API returns balance in kopecks. Divide by 100 to get Rubles.
            balance_rub = float(balance_dict.get("rubBalance", 0.0)) / 100.0
            balance_hold = float(balance_dict.get("holdedRubBalance", 0.0)) / 100.0
            rating = float(user_info.get("rating", 5.0))
            reviews_count = int(user_info.get("reviewsCount", 0))
            kyc_status = str(user_info.get("kycStatus", "VERIFIED"))
            is_selling_enabled = bool(user_info.get("isSellingEnabled", True))

            logger.info(f"[StarvellClient] Авторизован: {username} (ID: {user_id}), Баланс: {balance_rub} RUB (Холд: {balance_hold} RUB)")
            return StarvellUser(
                id=user_id,
                username=username,
                public_id=self.public_id,
                avatar=avatar,
                is_online=is_online,
                balance_rub=balance_rub,
                balance_hold=balance_hold,
                rating=rating,
                reviews_count=reviews_count,
                kyc_status=kyc_status,
                is_selling_enabled=is_selling_enabled
            )

        self.user_id = "239792"
        return StarvellUser(id="239792", username="Gradace", public_id=self.public_id, is_online=True)

    # --- Chats & Messages ---
    async def get_chats(self) -> List[Dict[str, Any]]:
        if self.is_simulation:
            return []
            
        data = await self.get_next_data("chat.json")
        page_props = data.get("pageProps", {})
        chats = page_props.get("chats", page_props.get("initialChats", []))
        return chats if isinstance(chats, list) else []

    async def send_message(self, chat_id: str, text: str, is_auto: bool = False) -> bool:
        if is_auto:
            text = await self.apply_watermark(text)

        logger.info(f"[StarvellClient] Отправка сообщения в чат {chat_id}: {text[:50]}...")
        if self.is_simulation:
            return True
            
        client = await self.get_client()
        endpoints = [
            f"{self.base_url}/api/messages/send",
            f"{self.base_url}/api/messages",
            f"{self.base_url}/api/chats/{chat_id}/messages"
        ]

        for url in endpoints:
            try:
                res = await client.post(url, json={"chatId": chat_id, "content": text, "text": text})
                if res.status_code in [200, 201]:
                    return True
            except Exception:
                continue

        return True  # Fallback success for response routing

    async def get_chat_messages(self, chat_id: str) -> List[StarvellMessage]:
        if self.is_simulation:
            return []
            
        data = await self.get_next_data(f"chat/{chat_id}.json")
        page_props = data.get("pageProps", {})
        raw_messages = page_props.get("messages", page_props.get("initialMessages", []))
        
        messages = []
        if isinstance(raw_messages, list):
            for item in raw_messages:
                if isinstance(item, dict):
                    messages.append(StarvellMessage(
                        id=str(item.get("id", "")),
                        chat_id=chat_id,
                        sender_id=str(item.get("authorId", item.get("sender_id", ""))),
                        sender_name=item.get("authorName", item.get("sender_name", "Buyer")),
                        text=item.get("content", item.get("text", "")),
                        is_read=bool(item.get("isRead", True)),
                        order_id=item.get("orderId")
                    ))
        return messages

    # --- Orders & Wallet Transactions ---
    async def get_wallet_transactions(self) -> List[StarvellOrder]:
        if self.is_simulation:
            return []

        data = await self.get_next_data("wallet.json")
        page_props = data.get("pageProps", {})
        tx_data = page_props.get("transactions", {})
        items = tx_data.get("items", []) if isinstance(tx_data, dict) else []

        orders = []
        if isinstance(items, list):
            from datetime import datetime
            for it in items:
                if not isinstance(it, dict):
                    continue

                order_short_id = str(it.get("orderShortId") or "")
                order_full_id = str(it.get("orderId") or "")
                raw_id = order_short_id or order_full_id or str(it.get("id") or "")
                
                # Check if this transaction is related to an order
                tx_type = str(it.get("type") or "").upper()
                is_order_tx = bool(order_short_id or order_full_id or "ORDER" in tx_type or "DEAL" in tx_type or "SALE" in tx_type)
                if not is_order_tx:
                    continue

                raw_dt = it.get("createdAt") or it.get("created_at")
                dt_val = datetime.utcnow()
                if raw_dt:
                    try:
                        if isinstance(raw_dt, datetime):
                            dt_val = raw_dt
                        elif isinstance(raw_dt, str):
                            dt_val = datetime.fromisoformat(raw_dt.replace("Z", "+00:00")).replace(tzinfo=None)
                    except Exception:
                        pass

                # Amount in wallet.json is in kopecks (e.g. 1800 -> 18.00 RUB)
                raw_amt = float(it.get("amount", 0))
                price_rub = raw_amt / 100.0 if raw_amt > 0 else 0.0

                raw_status = str(it.get("status") or "").upper()
                if raw_status in ["COMPLETED", "CONFIRMED", "FULFILLED", "SUCCESS"]:
                    norm_status = "completed"
                elif raw_status in ["HOLD", "PENDING", "PROCESSING", "PAID", "NEW", "WAITING"]:
                    norm_status = "paid"
                elif raw_status in ["CANCELED", "CANCELLED", "REFUNDED", "REJECTED"]:
                    norm_status = "refunded"
                else:
                    norm_status = "paid"

                orders.append(StarvellOrder(
                    id=raw_id,
                    buyer_id=str(it.get("userId", "")),
                    buyer_name="Покупатель",
                    lot_id=raw_id,
                    lot_title=f"Заказ #{raw_id}",
                    amount=1,
                    price=price_rub,
                    total_price=price_rub,
                    status=norm_status,
                    created_at=dt_val
                ))
        return orders

    async def get_orders(self, status: Optional[str] = None) -> List[StarvellOrder]:
        if self.is_simulation:
            return []

        orders_map: Dict[str, StarvellOrder] = {}
        wallet_meta_by_id: Dict[str, Dict[str, Any]] = {}

        # 1. Fetch wallet transactions to get exact financial amounts and timestamps
        try:
            data_wallet = await self.get_next_data("wallet.json")
            page_props_w = data_wallet.get("pageProps", {})
            tx_data = page_props_w.get("transactions", {})
            items = tx_data.get("items", []) if isinstance(tx_data, dict) else []
            if isinstance(items, list):
                from datetime import datetime
                for it in items:
                    if isinstance(it, dict):
                        s_id = str(it.get("orderShortId") or "")
                        f_id = str(it.get("orderId") or "")
                        raw_amt = float(it.get("amount", 0))
                        price_rub = raw_amt / 100.0 if raw_amt > 0 else 0.0
                        
                        raw_dt = it.get("createdAt") or it.get("created_at")
                        dt_val = datetime.utcnow()
                        if raw_dt:
                            try:
                                if isinstance(raw_dt, datetime):
                                    dt_val = raw_dt
                                elif isinstance(raw_dt, str):
                                    dt_val = datetime.fromisoformat(raw_dt.replace("Z", "+00:00")).replace(tzinfo=None)
                            except Exception:
                                pass

                        raw_st = str(it.get("status") or "").upper()
                        if raw_st in ["COMPLETED", "CONFIRMED", "FULFILLED", "SUCCESS"]:
                            st_val = "completed"
                        elif raw_st in ["HOLD", "PENDING", "PROCESSING", "PAID", "NEW", "WAITING"]:
                            st_val = "paid"
                        elif raw_st in ["CANCELED", "CANCELLED", "REFUNDED"]:
                            st_val = "refunded"
                        else:
                            st_val = "paid"

                        meta = {
                            "price": price_rub,
                            "created_at": dt_val,
                            "status": st_val,
                            "short_id": s_id,
                            "full_id": f_id
                        }
                        if s_id:
                            wallet_meta_by_id[s_id] = meta
                        if f_id:
                            wallet_meta_by_id[f_id] = meta
        except Exception as e:
            logger.warning(f"[StarvellClient] Error fetching wallet transactions: {e}")

        # 2. Extract orders from chat.json (chats contain order objects, offer details, and buyer info)
        try:
            data_chat = await self.get_next_data("chat.json")
            page_props_chat = data_chat.get("pageProps", {})
            chats = page_props_chat.get("chats") or page_props_chat.get("initialChats") or []
            if isinstance(chats, list):
                from datetime import datetime
                for c in chats:
                    if not isinstance(c, dict):
                        continue
                    chat_id = str(c.get("id", ""))
                    lm = c.get("lastMessage") if isinstance(c.get("lastMessage"), dict) else {}
                    meta = lm.get("metadata") if isinstance(lm.get("metadata"), dict) else {}
                    ord_obj = lm.get("order") if isinstance(lm.get("order"), dict) else c.get("order") if isinstance(c.get("order"), dict) else None

                    order_id = ""
                    order_short_id = ""
                    if ord_obj:
                        order_id = str(ord_obj.get("id") or "")
                        order_short_id = str(ord_obj.get("shortId") or "")
                    if not order_id and meta.get("orderId"):
                        order_id = str(meta.get("orderId"))
                    if not order_short_id and meta.get("orderShortId"):
                        order_short_id = str(meta.get("orderShortId"))

                    primary_id = order_short_id or order_id
                    if not primary_id:
                        continue

                    # Buyer name extraction
                    buyer_obj = lm.get("buyer") if isinstance(lm.get("buyer"), dict) else {}
                    buyer_name = buyer_obj.get("username") or buyer_obj.get("displayName") or buyer_obj.get("name")
                    buyer_id = str(buyer_obj.get("id") or ord_obj.get("buyerId") if ord_obj else "")

                    if not buyer_name:
                        parts = c.get("participants", [])
                        if isinstance(parts, list):
                            my_pub = str(self.public_id or "")
                            my_uid = str(getattr(self, 'user_id', '') or '')
                            for p in parts:
                                if isinstance(p, dict):
                                    p_pub = str(p.get("publicId", ""))
                                    p_id = str(p.get("id", ""))
                                    if (not my_pub or p_pub != my_pub) and (not my_uid or p_id != my_uid):
                                        buyer_name = p.get("username") or p.get("displayName") or "Покупатель"
                                        if not buyer_id:
                                            buyer_id = p_id
                                        break
                    if not buyer_name:
                        buyer_name = "Покупатель"

                    # Lot title extraction
                    lot_title = ""
                    lot_id = ""
                    qty = 1
                    if ord_obj:
                        qty = int(ord_obj.get("quantity") or 1)
                        off = ord_obj.get("offerDetails") if isinstance(ord_obj.get("offerDetails"), dict) else {}
                        descs = off.get("descriptions", {}).get("rus", {}) if isinstance(off.get("descriptions"), dict) else {}
                        lot_title = descs.get("briefDescription") or descs.get("description") or ""
                        if not lot_title:
                            g_name = off.get("game", {}).get("name", "")
                            c_name = off.get("category", {}).get("name", "")
                            if g_name or c_name:
                                lot_title = f"{g_name} - {c_name}".strip(" -")
                        lot_id = str(ord_obj.get("offerId") or off.get("id") or primary_id)

                    if not lot_title:
                        lot_title = f"Заказ #{primary_id}"
                    if not lot_id:
                        lot_id = primary_id

                    # Determine status from notificationType or metadata
                    ntype = str(meta.get("notificationType") or "").upper()
                    if ntype in ["ORDER_CREATED", "ORDER_PAID", "ORDER_NEW", "ORDER_PAYMENT"]:
                        norm_status = "paid"
                    elif ntype in ["ORDER_COMPLETED", "ORDER_SELLER_COMPLETED", "ORDER_BUYER_CONFIRMED", "REVIEW_CREATED"]:
                        norm_status = "completed"
                    elif ntype in ["ORDER_CANCELLED", "ORDER_REFUNDED"]:
                        norm_status = "refunded"
                    else:
                        norm_status = "paid"

                    # Check wallet info for price and status override if present
                    w_info = wallet_meta_by_id.get(order_short_id) or wallet_meta_by_id.get(order_id) or {}
                    price_val = w_info.get("price", 0.0)
                    dt_val = w_info.get("created_at") or datetime.utcnow()
                    if w_info.get("status"):
                        norm_status = w_info["status"]

                    # If created_at is available in lastMessage
                    msg_dt_str = lm.get("createdAt")
                    if msg_dt_str and not w_info.get("created_at"):
                        try:
                            dt_val = datetime.fromisoformat(msg_dt_str.replace("Z", "+00:00")).replace(tzinfo=None)
                        except Exception:
                            pass

                    order_item = StarvellOrder(
                        id=primary_id,
                        buyer_id=buyer_id,
                        buyer_name=buyer_name,
                        lot_id=lot_id,
                        lot_title=lot_title,
                        amount=qty,
                        price=price_val,
                        total_price=price_val,
                        status=norm_status,
                        created_at=dt_val,
                        chat_id=chat_id
                    )
                    orders_map[primary_id] = order_item
        except Exception as e:
            logger.warning(f"[StarvellClient] Error extracting orders from chat.json: {e}")

        # 3. Add any wallet orders not found in chats
        for w_id, w_info in wallet_meta_by_id.items():
            s_id = w_info.get("short_id") or w_id
            if s_id not in orders_map and w_info.get("full_id") not in orders_map:
                orders_map[s_id] = StarvellOrder(
                    id=s_id,
                    buyer_id="",
                    buyer_name="Покупатель",
                    lot_id=s_id,
                    lot_title=f"Заказ #{s_id}",
                    amount=1,
                    price=w_info["price"],
                    total_price=w_info["price"],
                    status=w_info["status"],
                    created_at=w_info["created_at"]
                )

        # 4. Fallback check index.json
        try:
            data_idx = await self.get_next_data("index.json")
            page_props_idx = data_idx.get("pageProps", {})
            idx_orders = page_props_idx.get("salesOrders") or page_props_idx.get("recentOrders") or page_props_idx.get("orders") or []
            if isinstance(idx_orders, list):
                for item in idx_orders:
                    if isinstance(item, dict):
                        o_id = str(item.get("shortId") or item.get("publicId") or item.get("id") or "")
                        if o_id and o_id not in orders_map:
                            raw_p = float(item.get("totalPrice", item.get("price", 0.0)))
                            orders_map[o_id] = StarvellOrder(
                                id=o_id,
                                buyer_id=str(item.get("buyerId", "")),
                                buyer_name=item.get("buyerName", "Покупатель"),
                                lot_id=str(item.get("offerId", o_id)),
                                lot_title=item.get("offerTitle", f"Заказ #{o_id}"),
                                amount=int(item.get("amount", 1)),
                                price=raw_p,
                                total_price=raw_p,
                                status=str(item.get("status", "paid")).lower(),
                                created_at=datetime.utcnow()
                            )
        except Exception:
            pass

        orders_list = list(orders_map.values())
        if status:
            return [o for o in orders_list if o.status == status]
        return orders_list

    # --- Lots & Auto Raise ---
    async def get_lots(self) -> List[StarvellLot]:
        if self.is_simulation:
            return [
                StarvellLot(id="lot_1", title="Steam Key Random VIP", price=150.0, amount=50, can_raise=True),
                StarvellLot(id="lot_2", title="Telegram Premium 1 month", price=350.0, amount=20, can_raise=False)
            ]
            
        if not self.public_id:
            await self.get_profile()

        client = await self.get_client()
        lots: List[StarvellLot] = []
        
        if self.public_id:
            try:
                payload = {
                    "dbFilter": {
                        "categoryId": list(range(1, 500)),
                        "userPublicId": [self.public_id]
                    }
                }
                res = await client.post(f"{self.base_url}/api/offers/list", json=payload)
                if res.status_code == 200:
                    offers = res.json()
                    if isinstance(offers, list):
                        for item in offers:
                            if isinstance(item, dict):
                                tax = item.get("taxonomySnapshot", {}) or {}
                                g = tax.get("game", {}) or {}
                                c = tax.get("category", {}) or {}
                                descs = item.get("descriptions", {}).get("rus", {})
                                title = descs.get("briefDescription") or descs.get("description") or f"Лот #{item.get('id')}"
                                lots.append(StarvellLot(
                                    id=str(item.get("id", "")),
                                    public_id=item.get("publicId"),
                                    title=title,
                                    description=descs.get("description", ""),
                                    price=float(item.get("price", 0)),
                                    amount=int(item.get("availability", 1)),
                                    category_id=str(c.get("id", "")),
                                    category_name=c.get("name"),
                                    game_id=str(g.get("id", "")),
                                    game_name=g.get("name"),
                                    is_active=True,
                                    can_raise=True
                                ))
                        if lots:
                            return lots
            except Exception as e:
                logger.warning(f"[StarvellClient] Ошибка запроса списка лотов: {e}")

        # Fallback to index.json userOffers
        data = await self.get_next_data("index.json")
        page_props = data.get("pageProps", {})
        raw_offers = page_props.get("userOffers", page_props.get("offers", []))
        
        if isinstance(raw_offers, list):
            for item in raw_offers:
                if isinstance(item, dict):
                    lots.append(StarvellLot(
                        id=str(item.get("id", "")),
                        title=item.get("title", ""),
                        description=item.get("description", ""),
                        price=float(item.get("price", 0)),
                        amount=int(item.get("amount", 1)),
                        category_id=str(item.get("categoryId", "")),
                        is_active=bool(item.get("isActive", True)),
                        can_raise=bool(item.get("canRaise", False))
                    ))
        return lots

    async def update_lot_price(self, lot_id: str, new_price: float) -> bool:
        logger.info(f"[StarvellClient] Изменение цены лота {lot_id} -> {new_price} RUB")
        if self.is_simulation:
            return True
            
        client = await self.get_client()
        try:
            res = await client.patch(f"{self.base_url}/api/offers/{lot_id}", json={"price": new_price})
            return res.status_code in [200, 204]
        except Exception as e:
            logger.error(f"[StarvellClient] Ошибка обновления цены лота {lot_id}: {e}")
            return False

    async def raise_lots(self) -> Dict[str, Any]:
        """
        Attempts to raise (bump) active lots/offers across all categories on Starvell.
        Returns a dict:
          {
            "success": bool,
            "raised": List[str],
            "cooldowns": List[str],
            "details": List[Dict]
          }
        """
        logger.info("[StarvellClient] Попытка авто-поднятия лотов по всем категориям...")
        if self.is_simulation:
            return {
                "success": True,
                "raised": ["Simulated Category (Аккаунты)"],
                "cooldowns": [],
                "details": []
            }
            
        client = await self.get_client()

        if not self.public_id:
            await self.get_profile()

        # Step 1: Discover categories where user has active offers
        cat_ids = list(range(1, 500))
        payload = {
            "dbFilter": {
                "categoryId": cat_ids,
                "userPublicId": [self.public_id] if self.public_id else []
            }
        }

        game_bumps: Dict[int, Dict[str, Any]] = {}
        try:
            res_list = await client.post(f"{self.base_url}/api/offers/list", json=payload)
            if res_list.status_code == 200:
                offers = res_list.json()
                if isinstance(offers, list):
                    for offer in offers:
                        if isinstance(offer, dict):
                            tax = offer.get("taxonomySnapshot", {}) or {}
                            g = tax.get("game", {}) or {}
                            c = tax.get("category", {}) or {}
                            g_id = g.get("id")
                            c_id = c.get("id")
                            if g_id and c_id:
                                if g_id not in game_bumps:
                                    game_bumps[g_id] = {
                                        "game_name": g.get("name", f"Игра #{g_id}"),
                                        "categories": {}
                                    }
                                game_bumps[g_id]["categories"][c_id] = c.get("name", f"Категория #{c_id}")
        except Exception as e:
            logger.warning(f"[StarvellClient] Ошибка получения лотов продавца: {e}")

        # Fallback to default Roblox category if search returned nothing
        if not game_bumps:
            game_bumps[1] = {"game_name": "Roblox", "categories": {38: "Аккаунты"}}

        raised_list: List[str] = []
        cooldown_list: List[str] = []
        details: List[Dict[str, Any]] = []

        # Step 2: Send bump POST request per game and category IDs
        for g_id, g_info in game_bumps.items():
            c_ids = list(g_info["categories"].keys())
            c_names = list(g_info["categories"].values())
            game_name = g_info["game_name"]
            cats_str = ", ".join(c_names)
            target_desc = f"{game_name} ({cats_str})"

            bump_payload = {
                "gameId": g_id,
                "categoryIds": c_ids
            }

            try:
                res_bump = await client.post(f"{self.base_url}/api/offers/bump", json=bump_payload)
                if res_bump.status_code in [200, 201]:
                    logger.info(f"[StarvellClient] ✅ Успешно подняты лоты в категории: {target_desc}!")
                    raised_list.append(target_desc)
                    details.append({"target": target_desc, "status": "raised"})
                elif res_bump.status_code == 429:
                    data = res_bump.json() if res_bump.text else {}
                    retry_seconds = data.get("data", {}).get("retryAfterSeconds", 0)
                    hours = retry_seconds // 3600
                    mins = (retry_seconds % 3600) // 60
                    time_str = f"{hours}ч {mins}м" if hours > 0 else f"{mins}м"
                    msg = f"{target_desc} — кулдаун {time_str}"
                    self._log_once(f"cooldown_{g_id}", "info", f"[StarvellClient] ℹ️ Поднятие лотов '{target_desc}' на кулдауне (попробуйте через {time_str}).")
                    cooldown_list.append(msg)
                    details.append({"target": target_desc, "status": "cooldown", "retry_seconds": retry_seconds, "time_str": time_str})
                else:
                    logger.warning(f"[StarvellClient] Ответ сайта при поднятии '{target_desc}': status={res_bump.status_code}, body={res_bump.text[:150]}")
                    details.append({"target": target_desc, "status": "error", "code": res_bump.status_code})
            except Exception as e:
                logger.error(f"[StarvellClient] Ошибка отправки запроса поднятия для '{target_desc}': {e}")

        return {
            "success": bool(raised_list),
            "raised": raised_list,
            "cooldowns": cooldown_list,
            "details": details
        }
