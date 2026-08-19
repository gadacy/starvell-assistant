from services.plugin_api import BasePlugin, PluginContext
from starvell.models import StarvellEvent

class AutoThankYouPlugin(BasePlugin):
    PLUGIN_NAME = "AutoThankYou"
    PLUGIN_VERSION = "1.0.0"
    PLUGIN_DESCRIPTION = "Отправляет персонализированную благодарность клиенту после оплаты заказа."
    PLUGIN_AUTHOR = "gadacy"

    settings_schema = [
        {
            "key": "thankyou_text",
            "label": "Текст благодарности",
            "type": "text",
            "default": "Большое спасибо за ваш заказ! Будем рады видеть вас снова! ❤️"
        },
        {
            "key": "notify_admin",
            "label": "Уведомлять в TG",
            "type": "bool",
            "default": True
        }
    ]

    async def on_event(self, event: StarvellEvent):
        if not self.context:
            return

        if event.event_type == "order_paid" and event.order:
            text = await self.context.get_setting(
                "thankyou_text",
                "Большое спасибо за ваш заказ! Будем рады видеть вас снова! ❤️"
            )
            chat_id = event.order.chat_id or event.order.buyer_id
            if chat_id:
                await self.context.send_starvell_message(chat_id, text)

            notify = await self.context.get_setting("notify_admin", True)
            if notify:
                await self.context.send_admin_notification(
                    f"💖 **[Plugin AutoThankYou]** Отправлена благодарность покупателю {event.order.buyer_name} по заказу #{event.order.id}!"
                )
