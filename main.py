import importlib
import asyncio
import sys
from sqlalchemy import select
import config
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
import version
from services.update_checker import UpdateCheckerService, restart_event
from core.banner import print_banner

async def run_bot_instance() -> bool:
    """
    Runs a single instance of the bot.
    Returns True if soft restart was requested, False if shutdown.
    """
    restart_event.clear()
    cfg = config.config

    # Check if configured or launch setup
    if not cfg.starvell_api_key and not cfg.telegram_bot_token:
        logger.warning("[Main] Bot is unconfigured. Starting setup wizard...")
        print("\n⚠️ Конфигурация бота не найдена или пуста!")
        run_wizard = input("Желаете запустить Мастер Настройки (setup.py)? (Y/n): ").strip().lower()
        if run_wizard != "n":
            from setup import run_setup
            run_setup()
            return False

    # 1. Initialize Database
    await init_db()
    logger.info("[Main] Database initialized.")

    # 2. Initialize Starvell API Client
    starvell_client = StarvellClient(api_key=cfg.starvell_api_key)
    if cfg.simulation_mode:
        starvell_client.is_simulation = True

    if starvell_client.is_simulation:
        logger.info("--------------------------------------------------")
        logger.info("🛠️ Бот запущен в РЕЖИМЕ СИМУЛЯЦИИ (Dry-Run Mode).")
        logger.info("Все функции бота работают локально без реальных списаний/запросов.")
        logger.info("--------------------------------------------------")
    else:
        try:
            await starvell_client.get_profile()
        except Exception as e:
            logger.warning(f"[Main] Не удалось предзагрузить профиль при старте: {e}")

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
    await chat_relay.init_seen_chats()
    review_reminder = ReviewReminderService(client=starvell_client, check_interval=300, delay_minutes=15)

    # 4. Event Handler Routing
    async def process_order_event(event: StarvellEvent):
        order = event.order
        if not order:
            return

        order_chat_id = str(order.chat_id or order.buyer_id or "")
        if order_chat_id:
            await chat_relay.mark_chat_seen(order_chat_id)

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
            if bot_inst and cfg.telegram_admin_ids:
                import html
                from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                from core.database.models import StockItem, AutoResponse

                safe_id = html.escape(str(order.id))
                safe_title = html.escape(str(order.lot_title or "Товар"))
                safe_buyer = html.escape(str(order.buyer_name or "Покупатель"))
                price = order.total_price or order.price or 0.0

                chat_id = order.chat_id or order.buyer_id
                order_url = f"https://starvell.com/chat/{chat_id}" if chat_id else f"https://starvell.com"

                buttons = []
                if chat_id:
                    buttons.append([
                        InlineKeyboardButton(text="✉️ Ответить", callback_data=f"reply_chat_{chat_id}"),
                        InlineKeyboardButton(text="📝 Заготовки", callback_data=f"quick_replies_{chat_id}")
                    ])
                buttons.append([
                    InlineKeyboardButton(text="🌐 Открыть чат / заказ", url=order_url),
                    InlineKeyboardButton(text="💸 Возврат средств", callback_data=f"refund_order_{safe_id}")
                ])

                kb = InlineKeyboardMarkup(inline_keyboard=buttons)

                if status in ["paid", "new"]:
                    async with AsyncSessionLocal() as db_session:
                        # Check auto delivery setting
                        res_ad = await db_session.execute(select(BotSetting).where(BotSetting.key == "auto_delivery_enabled"))
                        set_ad = res_ad.scalar_one_or_none()
                        ad_enabled = set_ad.value.lower() == "true" if set_ad else True

                        stock_res = await db_session.execute(
                            select(StockItem).where(StockItem.lot_id == str(order.lot_id), StockItem.is_used == False).limit(1)
                        )
                        has_stock = stock_res.scalar_one_or_none() is not None

                        template_res = await db_session.execute(
                            select(AutoResponse).where(
                                AutoResponse.trigger_type == "order_paid",
                                AutoResponse.lot_id == str(order.lot_id),
                                AutoResponse.is_active == True
                            ).limit(1)
                        )
                        has_template = template_res.scalar_one_or_none() is not None

                    if not ad_enabled:
                        delivery_info = "ℹ️ <b>Авто-выдача:</b> <i>Отключена в настройках бота.</i>"
                    elif has_stock or has_template:
                        delivery_info = "⚡ <b>Авто-выдача:</b> <i>Товар выдается автоматически!</i>"
                    else:
                        delivery_info = "⚠️ <b>Авто-выдача:</b> <i>Нет привязанного ключа/шаблона. Требуется ручная выдача!</i>"

                    qty_str = f"🔢 <b>Количество:</b> {order.amount} шт.\n" if order.amount and order.amount > 1 else ""
                    buyer_str = f"<a href='https://starvell.com/profile/{safe_buyer}'>{safe_buyer}</a>" if safe_buyer != "Покупатель" else safe_buyer

                    msg_text = (
                        f"🛍 <b>Новая покупка на Starvell!</b>\n\n"
                        f"📦 <b>Товар:</b> {safe_title}\n"
                        f"👤 <b>Покупатель:</b> {buyer_str}\n"
                        f"💵 <b>Сумма:</b> {price:.2f} ₽\n"
                        f"{qty_str}"
                        f"🆔 <b>ID Заказа:</b> <code>#{safe_id}</code>\n\n"
                        f"{delivery_info}"
                    )
                elif status == "completed":
                    msg_text = (
                        f"🌕 <b>Заказ #{safe_id} подтвержден!</b>\n\n"
                        f"👤 Пользователь <b>{safe_buyer}</b> подтвердил выполнение заказа.\n"
                        f"📦 <b>Товар:</b> {safe_title}\n"
                        f"💵 <b>Сумма:</b> {price:.2f} ₽"
                    )
                elif status in ["cancelled", "canceled", "refunded"]:
                    msg_text = (
                        f"❌ <b>Заказ #{safe_id} отменен!</b>\n\n"
                        f"👤 Пользователь <b>{safe_buyer}</b> или администратор отменил заказ.\n"
                        f"📦 <b>Товар:</b> {safe_title}\n"
                        f"💵 <b>Сумма:</b> {price:.2f} ₽"
                    )
                else:
                    msg_text = f"📦 <b>Обновление статуса заказа #{safe_id}:</b> {html.escape(status)}"

                for admin_id in cfg.telegram_admin_ids:
                    try:
                        await bot_inst.send_message(admin_id, msg_text, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)
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
        elif event.event_type == "self_message" and event.chat_id:
            await chat_relay.update_chat_activity(event.chat_id)
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

    async def check_updates_background():
        await asyncio.sleep(5.0)
        has_update, msg_text, _ = await UpdateCheckerService.check_for_updates()
        if has_update:
            logger.info(f"[Main] {msg_text}")
            await send_admin_notification(msg_text)

    asyncio.create_task(check_updates_background())

    # 5. Initialize Telegram Bot
    bot, dp = init_telegram_bot()
    bot_task = None
    if bot and dp:
        bot_task = asyncio.create_task(dp.start_polling(bot))

    await send_admin_startup_panel()

    restart_requested = False
    try:
        wait_task = asyncio.create_task(restart_event.wait())
        done, pending = await asyncio.wait([wait_task], return_when=asyncio.FIRST_COMPLETED)
        if wait_task in done and restart_event.is_set():
            logger.info("[Main] Получен сигнал мягкого перезапуска бота!")
            restart_requested = True
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("[Main] Завершение работы служб бота...")
    finally:
        logger.info("[Main] Остановка служб и завершение подключений...")
        await listener.stop()
        await auto_raise.stop()
        await review_reminder.stop()
        await starvell_client.close()
        if bot and dp:
            await dp.stop_polling()
            if bot.session:
                await bot.session.close()
        if bot_task and not bot_task.done():
            bot_task.cancel()
        logger.info("[Main] Инстанс бота успешно остановлен.")

    return restart_requested

async def main():
    print_banner()
    while True:
        logger.info(f"      🚀 Starting Starvell Assistant Bot (v{version.__version__})     ")
        should_restart = await run_bot_instance()
        if not should_restart:
            break
        logger.info("--------------------------------------------------")
        logger.info("🔄 [Main] Мягкий перезапуск всех служб в текущем окне...")
        logger.info("--------------------------------------------------")
        importlib.reload(config)
        importlib.reload(version)
        importlib.reload(features)
        importlib.reload(plugins)
        importlib.reload(stats)
        await asyncio.sleep(1.0)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
