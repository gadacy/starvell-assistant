import asyncio
import sys
from sqlalchemy import select
from config import config, save_config
from core.database.base import init_db, AsyncSessionLocal
from core.database.models import BotSetting
from core.logger import logger
from starvell.client import StarvellClient
from starvell.listener import StarvellListener
from starvell.models import StarvellEvent
from services.auto_responder import AutoResponderService
from services.auto_delivery import AutoDeliveryService
from services.auto_raise import AutoRaiseService
from services.chat_relay import ChatRelayService
from services.review_reminder import ReviewReminderService
from services.plugin_manager import PluginManager
from tg_bot.bot import init_telegram_bot, send_admin_notification, send_admin_startup_panel, get_bot
from tg_bot.handlers import features, plugins, stats
from core.banner import print_banner

async def main():
    print_banner()
    logger.info("      🚀 Starting Starvell Assistant Bot     ")

    # Check if configured or launch setup
    if not config.starvell_api_key and not config.telegram_bot_token:
        logger.warning("[Main] Bot is unconfigured. Starting setup wizard...")
        print("\n⚠️ Конфигурация бота не найдена или пуста!")
        run_wizard = input("Желаете запустить Мастер Настройки (setup.py)? (Y/n): ").strip().lower()
        if run_wizard != "n":
            from setup import run_setup
            run_setup()
            return

    # 1. Initialize Database
    await init_db()
    logger.info("[Main] Database initialized.")

    # 2. Initialize Starvell API Client
    starvell_client = StarvellClient(api_key=config.starvell_api_key)
    if config.simulation_mode:
        starvell_client.is_simulation = True

    if starvell_client.is_simulation:
        logger.info("--------------------------------------------------")
        logger.info("🛠️ Бот запущен в РЕЖИМЕ СИМУЛЯЦИИ (Dry-Run Mode).")
        logger.info("Все функции бота работают локально без реальных списаний/запросов.")
        logger.info("--------------------------------------------------")

    # Set client reference for handlers
    features.set_client(starvell_client)
    stats.set_client(starvell_client)

    # 3. Initialize Services & Plugin Manager
    plugin_manager = PluginManager(client=starvell_client)
    await plugin_manager.load_all_plugins()
    plugins.set_plugin_manager(plugin_manager)

    auto_responder = AutoResponderService(client=starvell_client)
    auto_delivery = AutoDeliveryService(client=starvell_client, telegram_notifier=send_admin_notification)
    auto_raise = AutoRaiseService(client=starvell_client, interval_seconds=1800)
    chat_relay = ChatRelayService(client=starvell_client)
    review_reminder = ReviewReminderService(client=starvell_client, check_interval=300, delay_minutes=15)

    # 4. Event Handler Routing
    async def process_order_event(event: StarvellEvent):
        order = event.order
        if not order:
            return

        status = (order.status or "").lower()

        # 1. Send Order Notification to Telegram if notify_new_orders is enabled
        async with AsyncSessionLocal() as session:
            res = await session.execute(
                select(BotSetting).where(BotSetting.key == "notify_new_orders")
            )
            setting = res.scalar_one_or_none()
            notify_enabled = setting.value.lower() == "true" if setting else True

        if notify_enabled:
            bot_inst = get_bot()
            if bot_inst and config.telegram_admin_ids:
                import html
                from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

                safe_id = html.escape(str(order.id))
                safe_title = html.escape(str(order.lot_title or "Товар"))
                safe_buyer = html.escape(str(order.buyer_name or "Покупатель"))
                safe_buyer_id = html.escape(str(order.buyer_id or ""))
                price = order.total_price or order.price or 0.0

                chat_id = order.chat_id or order.buyer_id
                kb = None
                if chat_id:
                    kb = InlineKeyboardMarkup(inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="✍️ Чат с покупателем",
                                callback_data=f"reply_chat_{chat_id}"
                            )
                        ]
                    ])

                if status in ["paid", "new"]:
                    header = "🎉 <b>Оплачен новый заказ!</b>"
                elif status == "completed":
                    header = "✅ <b>Заказ успешно завершен!</b>"
                elif status in ["cancelled", "canceled", "refunded"]:
                    header = "❌ <b>Заказ отменен / возврат!</b>"
                else:
                    header = f"📦 <b>Обновление статуса заказа ({html.escape(status)})</b>"

                msg_text = (
                    f"{header}\n"
                    f"📦 <b>Заказ:</b> #{safe_id}\n"
                    f"🛒 <b>Лот:</b> {safe_title}\n"
                    f"👤 <b>Покупатель:</b> {safe_buyer} (<code>{safe_buyer_id}</code>)\n"
                    f"💵 <b>Сумма:</b> {price:.2f} RUB"
                )

                for admin_id in config.telegram_admin_ids:
                    try:
                        await bot_inst.send_message(admin_id, msg_text, reply_markup=kb, parse_mode="HTML")
                        logger.info(f"[OrderRelay] Sent order notification for order #{order.id} ({status}) to admin {admin_id}")
                    except Exception as e:
                        logger.error(f"[OrderRelay] Error sending order notification to admin {admin_id}: {e}")

        # 2. Trigger Auto-delivery for paid / new orders
        if status in ["paid", "new"]:
            await auto_delivery.process_order(order)

    async def on_starvell_event(event: StarvellEvent):
        logger.info(f"[EventDispatcher] Received event: {event.event_type}")
        if event.event_type == "new_message" and event.message:
            await chat_relay.process_incoming_message(event.message, event.order)
            await auto_responder.process_message(event.message, event.order)
        elif event.event_type.startswith("order_") and event.order:
            await process_order_event(event)

        # Dispatch event to active plugins
        await plugin_manager.dispatch_event(event)

    listener = StarvellListener(client=starvell_client, poll_interval=3.0)
    listener.register_handler(on_starvell_event)

    # Start background loops
    await listener.start()
    await auto_raise.start()
    await review_reminder.start()

    # 5. Initialize Telegram Bot
    bot, dp = init_telegram_bot()
    bot_task = None
    if bot and dp:
        bot_task = asyncio.create_task(dp.start_polling(bot))

    await send_admin_startup_panel()

    # Serve until cancelled
    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("[Main] Shutting down services...")
    finally:
        await listener.stop()
        await auto_raise.stop()
        await review_reminder.stop()
        await starvell_client.close()
        if bot_task:
            bot_task.cancel()
        logger.info("[Main] Starvell Assistant Bot stopped cleanly.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
