import importlib
import asyncio
import sys
from urllib.parse import quote
from sqlalchemy import select, func
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
from services.chat_state import record_order_purchase, save_reply_target
from services.review_reminder import ReviewReminderService
from services.plugin_manager import PluginManager
from tg_bot.bot import init_telegram_bot, send_admin_notification, send_admin_startup_panel, get_bot
from tg_bot.handlers import features, plugins, stats
import version
from services.update_checker import UpdateCheckerService, restart_event
from core.banner import print_banner

def ensure_config_ready() -> bool:
    """
    Ensures that config.json exists, is uncorrupted, and populated with credentials.
    If the configuration is missing, damaged, or empty, launches setup wizard directly
    in the current main.py window without requiring a separate script execution.
    Returns True if config is ready to proceed, False otherwise.
    """
    is_valid, status_code, message = config.check_config_status()
    if is_valid:
        return True

    print_banner()

    if status_code == "corrupted":
        logger.warning(f"[Main] {message}")
        print("=" * 64)
        print("❌ ВНИМАНИЕ: Файл конфигурации повреждён или имеет неверный формат!")
        print(f"   Детали: {message}")
        print("🛠️ Запуск встроенного мастера настройки setup.py для восстановления...")
        print("=" * 64 + "\n")
    elif status_code == "missing":
        logger.info(f"[Main] {message}")
        print("=" * 64)
        print("ℹ️ Файл конфигурации config.json не найден.")
        print("🛠️ Запуск встроенного мастера первоначальной настройки Starvell Assistant...")
        print("=" * 64 + "\n")
    elif status_code == "empty":
        logger.warning(f"[Main] {message}")
        print("=" * 64)
        print("⚠️ В конфигурации отсутствуют авторизационные данные.")
        print("🛠️ Запуск встроенного мастера настройки setup.py...")
        print("=" * 64 + "\n")

    if not sys.stdin.isatty():
        logger.error(
            f"[Main] {message} Терминал работает в неинтерактивном режиме (без TTY). "
            f"Автоматический запуск setup.py невозможен. Заполните config.json вручную."
        )
        return False

    from setup import run_setup
    success = run_setup(standalone=False)
    if not success:
        logger.warning("[Main] Мастер настройки не был завершен. Остановка бота.")
        return False

    is_valid_after, _, msg_after = config.check_config_status()
    if not is_valid_after:
        logger.error(f"[Main] Конфигурация всё ещё не готова: {msg_after}")
        return False

    return True

async def run_bot_instance() -> bool:
    """
    Runs a single instance of the bot.
    Returns True if soft restart was requested, False if shutdown.
    """
    restart_event.clear()

    # Ensure valid configuration or launch embedded setup wizard
    if not ensure_config_ready():
        return False

    cfg = config.config

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

        await record_order_purchase(order)

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

                link_buttons = []
                if order.full_id:
                    link_buttons.append(InlineKeyboardButton(text="🌐 Открыть заказ", url=f"https://starvell.com/order/{order.full_id}"))
                if chat_id:
                    link_buttons.append(InlineKeyboardButton(text="💬 Чат", url=f"https://starvell.com/chat/{chat_id}"))
                if not link_buttons:
                    link_buttons.append(InlineKeyboardButton(text="🌐 Открыть чат / заказ", url=order_url))

                buttons.append(link_buttons)
                buttons.append([
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
                            select(func.count(StockItem.id)).where(
                                StockItem.lot_id == str(order.lot_id), StockItem.is_used == False
                            )
                        )
                        has_stock = stock_res.scalar_one() >= max(1, int(order.amount or 1))

                        template_res = await db_session.execute(
                            select(AutoResponse).where(
                                AutoResponse.trigger_type == "order_paid",
                                AutoResponse.lot_id == str(order.lot_id),
                                AutoResponse.is_active == True
                            ).limit(1)
                        )
                        has_template = template_res.scalar_one_or_none() is not None

                    if status == "new":
                        delivery_info = "⏳ <b>Авто-выдача:</b> <i>Ожидает подтверждения оплаты.</i>"
                    elif not ad_enabled:
                        delivery_info = "ℹ️ <b>Авто-выдача:</b> <i>Отключена в настройках бота.</i>"
                    elif has_stock or has_template:
                        delivery_info = "⚡ <b>Авто-выдача:</b> <i>Товар выдается автоматически!</i>"
                    else:
                        delivery_info = "⚠️ <b>Авто-выдача:</b> <i>Нет привязанного ключа/шаблона. Требуется ручная выдача!</i>"

                    qty_str = f"🔢 <b>Количество:</b> {order.amount} шт.\n" if order.amount and order.amount > 1 else ""
                    buyer_url = f"https://starvell.com/profile/{quote(str(order.buyer_name), safe='')}"
                    buyer_str = f"<a href='{buyer_url}'>{safe_buyer}</a>" if safe_buyer != "Покупатель" else safe_buyer

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
                        sent = await bot_inst.send_message(admin_id, msg_text, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)
                        if chat_id:
                            await save_reply_target(sent.chat.id, sent.message_id, str(chat_id))
                        logger.info(f"[OrderRelay] Sent order notification for order #{order.id} ({status}) to admin {admin_id}")
                    except Exception as e:
                        logger.error(f"[OrderRelay] Error sending order notification to admin {admin_id}: {e}")

        # 2. Trigger Auto-delivery for paid / new orders
        if status in ["paid", "new"]:
            await auto_delivery.process_order(order)

    async def process_review_event(event: StarvellEvent):
        review = event.review
        if not review:
            return

        # Check if notify_reviews is enabled
        async with AsyncSessionLocal() as session:
            res = await session.execute(
                select(BotSetting).where(BotSetting.key == "notify_reviews")
            )
            setting = res.scalar_one_or_none()
            notify_enabled = setting.value.lower() == "true" if setting else True

        if not notify_enabled:
            return

        bot_inst = get_bot()
        if not bot_inst or not cfg.telegram_admin_ids:
            return

        import html
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

        safe_buyer = html.escape(str(review.buyer_name or "Покупатель"))
        safe_title = html.escape(str(review.lot_title or "Товар Starvell"))
        safe_content = html.escape(str(review.content or "").strip())
        ord_short = html.escape(str(review.order_short_id or review.order_id or ""))

        stars_str = review.stars_display
        rating_num = int(review.rating or 5)

        buyer_url = f"https://starvell.com/profile/{quote(str(review.buyer_name), safe='')}"
        buyer_link = f"<a href='{buyer_url}'>{safe_buyer}</a>" if (safe_buyer and not review.is_anonymous and safe_buyer != "Покупатель") else safe_buyer

        comment_block = f"💬 <b>Отзыв:</b> «<i>{safe_content}</i>»\n" if safe_content else "💬 <b>Отзыв:</b> <i>(Без текстового комментария)</i>\n"
        order_block = f"🆔 <b>Заказ:</b> <code>#{ord_short}</code>\n" if ord_short else ""

        msg_text = (
            f"⭐ <b>Новый отзыв на Starvell!</b>\n\n"
            f"⭐️ <b>Оценка:</b> {stars_str} ({rating_num}/5)\n"
            f"{comment_block}"
            f"📦 <b>Товар:</b> {safe_title}\n"
            f"👤 <b>Покупатель:</b> {buyer_link}\n"
            f"{order_block}"
        )

        buttons = []
        link_row = []
        if review.order_id:
            link_row.append(InlineKeyboardButton(text="🌐 Открыть заказ", url=f"https://starvell.com/order/{review.order_id}"))
        if review.chat_id:
            link_row.append(InlineKeyboardButton(text="💬 Чат", url=f"https://starvell.com/chat/{review.chat_id}"))
        elif not review.is_anonymous and review.buyer_name and review.buyer_name != "Покупатель":
            link_row.append(InlineKeyboardButton(text="👤 Профиль", url=buyer_url))

        if link_row:
            buttons.append(link_row)

        kb = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None

        for admin_id in cfg.telegram_admin_ids:
            try:
                await bot_inst.send_message(admin_id, msg_text, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)
                logger.info(f"[ReviewRelay] Sent review notification ({review.rating}⭐) to admin {admin_id}")
            except Exception as e:
                logger.error(f"[ReviewRelay] Error sending review notification to admin {admin_id}: {e}")

    async def on_starvell_event(event: StarvellEvent):
        logger.info(f"[EventDispatcher] Received event: {event.event_type}")
        if event.event_type == "new_message" and event.message:
            await chat_relay.process_incoming_message(event.message, event.order)
            await auto_responder.process_message(event.message, event.order)
        elif event.event_type == "self_message" and event.chat_id:
            await chat_relay.update_chat_activity(event.chat_id)
        elif event.event_type.startswith("order_") and event.order:
            await process_order_event(event)
        elif event.event_type == "new_review" and event.review:
            await process_review_event(event)

        # Dispatch event to active plugins
        await plugin_manager.dispatch_event(event)

    listener = StarvellListener(client=starvell_client, poll_interval=3.0)
    listener.register_handler(on_starvell_event)

    async def check_updates_background():
        await asyncio.sleep(5.0)
        has_update, msg_text, _ = await UpdateCheckerService.check_for_updates()
        if has_update:
            logger.info(f"[Main] {msg_text}")
            await send_admin_notification(msg_text)

    # 5. Initialize Telegram Bot
    bot, dp = init_telegram_bot()
    bot_task = None
    if bot and dp:
        bot_task = asyncio.create_task(dp.start_polling(bot))

    await send_admin_startup_panel()

    # Start event producers only after Telegram is ready to receive their notifications.
    await listener.start()
    await auto_raise.start()
    await review_reminder.start()
    update_task = asyncio.create_task(check_updates_background())

    restart_requested = False
    try:
        wait_task = asyncio.create_task(restart_event.wait())
        watched_tasks = [wait_task]
        if bot_task:
            watched_tasks.append(bot_task)
        done, pending = await asyncio.wait(watched_tasks, return_when=asyncio.FIRST_COMPLETED)
        if wait_task in done and restart_event.is_set():
            logger.info("[Main] Получен сигнал мягкого перезапуска бота!")
            restart_requested = True
        elif bot_task in done:
            if bot_task.cancelled():
                logger.warning("[Main] Telegram polling was cancelled.")
            elif bot_task.exception():
                logger.error(f"[Main] Telegram polling stopped with error: {bot_task.exception()}")
            else:
                logger.warning("[Main] Telegram polling stopped unexpectedly.")
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("[Main] Завершение работы служб бота...")
    finally:
        logger.info("[Main] Остановка служб и завершение подключений...")
        if not wait_task.done():
            wait_task.cancel()
        if not update_task.done():
            update_task.cancel()
        await asyncio.gather(wait_task, update_task, return_exceptions=True)
        await listener.stop()
        await auto_raise.stop()
        await review_reminder.stop()
        await plugin_manager.unload_all_plugins()
        await starvell_client.close()
        if bot and dp and bot_task and not bot_task.done():
            await dp.stop_polling()
        if bot_task and not bot_task.done():
            bot_task.cancel()
            await asyncio.gather(bot_task, return_exceptions=True)
        if bot:
            await bot.session.close()
        logger.info("[Main] Инстанс бота успешно остановлен.")

    return restart_requested

async def main():
    if not ensure_config_ready():
        return
    print_banner()
    while True:
        logger.info(f"      🚀 Starting Starvell Assistant Bot (v{version.__version__})     ")
        should_restart = await run_bot_instance()
        if not should_restart:
            break
        logger.info("--------------------------------------------------")
        logger.info("🔄 [Main] Мягкий перезапуск всех служб в текущем окне...")
        logger.info("--------------------------------------------------")
        if not ensure_config_ready():
            logger.warning("[Main] Конфигурация не готова после перезапуска. Завершение работы.")
            break
        # Keep the shared Config instance: handlers and middleware imported it directly.
        config.reload_config()
        importlib.reload(version)
        importlib.reload(features)
        importlib.reload(plugins)
        importlib.reload(stats)
        await asyncio.sleep(1.0)

if __name__ == "__main__":
    try:
        # Pre-check configuration before starting the event loop for smooth setup wizard experience
        if ensure_config_ready():
            asyncio.run(main())
    except KeyboardInterrupt:
        pass
