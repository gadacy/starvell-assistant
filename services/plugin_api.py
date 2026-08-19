import re
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from core.logger import logger
from starvell.models import StarvellOrder, StarvellLot, StarvellEvent

if TYPE_CHECKING:
    from starvell.client import StarvellClient
    from services.plugin_manager import PluginManager

class BasePlugin:
    """
    Base class for all Starvell Assistant plugins.
    """
    PLUGIN_NAME: str = "Unnamed Plugin"
    PLUGIN_VERSION: str = "1.0.0"
    PLUGIN_DESCRIPTION: str = "No description provided."
    PLUGIN_AUTHOR: str = "gadacy"
    
    # Example settings_schema format:
    # [
    #    {"key": "auto_reply", "label": "Авто-ответ", "type": "bool", "default": True},
    #    {"key": "greeting_text", "label": "Приветствие", "type": "text", "default": "Привет!"}
    # ]
    settings_schema: List[Dict[str, Any]] = []

    def __init__(self):
        self.context: Optional['PluginContext'] = None

    async def on_load(self, context: 'PluginContext'):
        """Called when plugin is enabled or loaded."""
        self.context = context

    async def on_unload(self):
        """Called when plugin is disabled or unloaded."""
        pass

    async def on_event(self, event: StarvellEvent):
        """Hook called when a new Starvell event arrives (messages, orders, etc)."""
        pass


class PluginContext:
    """
    Tool context provided to plugins giving access to bot tools, order details,
    message fragment extraction, settings storage, and messaging capabilities.
    """
    def __init__(self, plugin_name: str, client: 'StarvellClient', manager: 'PluginManager'):
        self.plugin_name = plugin_name
        self.client = client
        self.manager = manager

    async def get_orders(self, status: Optional[str] = None) -> List[StarvellOrder]:
        """Get list of orders, optionally filtered by status."""
        orders = await self.client.get_orders(status=status)
        if status:
            return [o for o in orders if o.status == status]
        return orders

    async def get_order_by_id(self, order_id: str) -> Optional[StarvellOrder]:
        """Find a specific order by ID/number."""
        clean_id = str(order_id).strip().lstrip("#")
        orders = await self.client.get_orders()
        for o in orders:
            if str(o.id) == clean_id:
                return o
        
        # Check DB OrderHistory fallback
        from sqlalchemy import select
        from core.database.base import AsyncSessionLocal
        from core.database.models import OrderHistory

        async with AsyncSessionLocal() as session:
            res = await session.execute(
                select(OrderHistory).where(OrderHistory.order_id == clean_id)
            )
            history = res.scalar_one_or_none()
            if history:
                return StarvellOrder(
                    id=history.order_id,
                    buyer_id=history.buyer_id,
                    buyer_name=history.buyer_name or "Buyer",
                    lot_id=history.lot_id,
                    lot_title=history.lot_title or "Digital Item",
                    price=history.price,
                    total_price=history.price,
                    status=history.status
                )
        return None

    async def get_order_desc(self, order_id: str) -> Dict[str, Any]:
        """
        Get detailed specs and description of an order.
        Returns a dictionary containing quantity/amount, lot title, pricing,
        status, buyer details, delivery data, and a ready-to-read text summary.
        """
        order = await self.get_order_by_id(order_id)
        if not order:
            return {
                "found": False,
                "order_id": order_id,
                "error": "Order not found",
                "summary": f"❌ Заказ #{order_id} не найден."
            }

        from sqlalchemy import select
        from core.database.base import AsyncSessionLocal
        from core.database.models import OrderHistory

        delivered_content = None
        async with AsyncSessionLocal() as session:
            res = await session.execute(
                select(OrderHistory).where(OrderHistory.order_id == str(order.id))
            )
            hist = res.scalar_one_or_none()
            if hist and hist.delivered_content:
                delivered_content = hist.delivered_content

        summary_lines = [
            f"📦 **Информация о заказе #{order.id}:**",
            f"• **Лот:** {order.lot_title} (ID: `{order.lot_id}`)",
            f"• **Количество штук (Amount):** {order.amount}",
            f"• **Цена за штуку:** {order.price:.2f} RUB",
            f"• **Итоговая стоимость:** {order.total_price:.2f} RUB",
            f"• **Статус:** {order.status}",
            f"• **Покупатель:** {order.buyer_name} (ID: `{order.buyer_id}`)"
        ]
        if delivered_content:
            summary_lines.append(f"• **Выданные данные:**\n`{delivered_content}`")

        return {
            "found": True,
            "order_id": order.id,
            "lot_id": order.lot_id,
            "lot_title": order.lot_title,
            "amount": order.amount,
            "price": order.price,
            "total_price": order.total_price,
            "status": order.status,
            "buyer_id": order.buyer_id,
            "buyer_name": order.buyer_name,
            "chat_id": order.chat_id,
            "delivered_content": delivered_content,
            "summary": "\n".join(summary_lines)
        }

    def get_message(self, text_or_obj: Any, pattern: Optional[str] = None, group: int = 0) -> str:
        """
        Extract full text or specific fragment/pattern from a message or string.
        - If pattern is None: returns full text.
        - If pattern is provided: uses regex to extract matching group (or full match if group=0).
        """
        if hasattr(text_or_obj, "text"):
            raw_text = str(text_or_obj.text or "")
        elif isinstance(text_or_obj, dict) and "text" in text_or_obj:
            raw_text = str(text_or_obj["text"] or "")
        else:
            raw_text = str(text_or_obj or "")

        if not pattern:
            return raw_text

        try:
            match = re.search(pattern, raw_text, re.IGNORECASE)
            if match:
                if group <= len(match.groups()):
                    return match.group(group) or ""
                return match.group(0) or ""
        except Exception as e:
            logger.warning(f"[PluginContext] Regex extraction error for pattern '{pattern}': {e}")

        return ""

    async def get_lots(self) -> List[StarvellLot]:
        """Get active lots of the seller."""
        return await self.client.get_lots()

    async def send_starvell_message(self, chat_id: str, text: str) -> bool:
        """Send message to buyer on Starvell marketplace chat."""
        return await self.client.send_message(chat_id=chat_id, text=text, is_auto=True)

    async def send_admin_notification(self, text: str):
        """Send notification to Telegram admin."""
        from tg_bot.bot import send_admin_notification
        await send_admin_notification(text)

    async def get_setting(self, key: str, default: Any = None) -> Any:
        """Get plugin setting value."""
        return await self.manager.get_plugin_setting(self.plugin_name, key, default)

    async def set_setting(self, key: str, value: Any):
        """Set plugin setting value."""
        await self.manager.set_plugin_setting(self.plugin_name, key, value)
