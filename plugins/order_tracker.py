from services.plugin_api import BasePlugin, PluginContext
from starvell.models import StarvellEvent

class OrderTrackerPlugin(BasePlugin):
    PLUGIN_NAME = "OrderTracker"
    PLUGIN_VERSION = "1.0.0"
    PLUGIN_DESCRIPTION = "Отслеживает и выводит детальную спецификацию заказов (количество, цена, покупатель)."
    PLUGIN_AUTHOR = "gadacy"

    settings_schema = [
        {"key": "auto_log_orders", "label": "Логировать новые заказы", "type": "bool", "default": True}
    ]

    async def on_load(self, context: PluginContext):
        await super().on_load(context)

    async def on_event(self, event: StarvellEvent):
        if not self.context:
            return

        should_log = await self.context.get_setting("auto_log_orders", True)
        if not should_log:
            return

        if event.event_type in ["order_paid", "order_new"] and event.order:
            order_id = event.order.id
            desc = await self.context.get_order_desc(order_id)
            if desc.get("found"):
                text = (
                    f"🧩 **[Plugin: OrderTracker] Новый заказ!**\n\n"
                    f"{desc.get('summary')}"
                )
                await self.context.send_admin_notification(text)
