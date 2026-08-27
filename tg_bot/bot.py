import asyncio
from typing import Optional
from aiogram import Bot, Dispatcher
from config import config
from core.logger import logger
from tg_bot.handlers import common, stock, auto_response, auto_delivery, stats, features, dumper, auto_raise, plugins
from tg_bot.middlewares import AdminAuthMiddleware

bot: Optional[Bot] = None
dp: Optional[Dispatcher] = None

def init_telegram_bot() -> tuple[Optional[Bot], Optional[Dispatcher]]:
    global bot, dp
    token = config.telegram_bot_token.strip()
    if not token or token.startswith("1234567890"):
        logger.warning("[TelegramBot] Token is empty or default in config. Telegram Bot disabled.")
        return None, None

    bot = Bot(token=token)
    dp = Dispatcher()

    # Register global admin whitelist security middleware
    admin_middleware = AdminAuthMiddleware()
    dp.message.outer_middleware(admin_middleware)
    dp.callback_query.outer_middleware(admin_middleware)

    # Register routers
    routers = [
        common.router,
        stock.router,
        auto_response.router,
        auto_delivery.router,
        stats.router,
        features.router,
        dumper.router,
        auto_raise.router,
        plugins.router
    ]
    for r in routers:
        r.parent_router = None
        dp.include_router(r)

    logger.info("[TelegramBot] Initialized Telegram Bot successfully.")
    return bot, dp

def get_bot() -> Optional[Bot]:
    return bot

async def send_admin_notification(text: str, parse_mode: Optional[str] = "HTML", reply_markup=None):
    if not bot or not config.telegram_admin_ids:
        return

    for admin_id in config.telegram_admin_ids:
        try:
            await bot.send_message(admin_id, text, parse_mode=parse_mode, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"[TelegramBot] Error sending notification to admin {admin_id}: {e}")
            if parse_mode:
                try:
                    await bot.send_message(admin_id, text, parse_mode=None, reply_markup=reply_markup)
                except Exception as ex:
                    logger.error(f"[TelegramBot] Error sending plain fallback notification to admin {admin_id}: {ex}")

async def setup_bot_profile():
    if not bot:
        return
    try:
        from aiogram.types import BotCommand
        short_desc = "Starvell Assistant Bot @starvell_assistant | github.com/gadacy/starvell-assistant"
        description = (
            "🤖 Starvell Assistant Bot — многофункциональный автобот для торговой площадки Starvell.com.\n\n"
            "📢 Канал проекта: @starvell_assistant\n"
            "🐙 GitHub: github.com/gadacy/starvell-assistant\n\n"
            "⚡ Возможности:\n"
            "• 💬 Живой чат & Пересылка сообщений\n"
            "• ⚡ Автовыдача и автоподнятие лотов\n"
            "• 📉 Демпинг цен и авто-ответчик\n"
            "• ⭐ Напоминалка про отзывы"
        )
        await bot.set_my_short_description(short_desc[:120])
        await bot.set_my_description(description)
        commands = [
            BotCommand(command="start", description="Главное меню управления"),
            BotCommand(command="profile", description="Профиль и статистика Starvell"),
            BotCommand(command="notifications", description="Настройки уведомлений"),
            BotCommand(command="restart", description="Перезапустить бота"),
            BotCommand(command="about", description="О боте и проекте")
        ]
        await bot.set_my_commands(commands)
        logger.info("[TelegramBot] Обновлено официальное описание бота в профиле Telegram.")
    except Exception as e:
        logger.error(f"[TelegramBot] Ошибка обновления описания бота: {e}")

async def send_admin_startup_panel():
    if not bot or not config.telegram_admin_ids:
        return

    await setup_bot_profile()

    from tg_bot.keyboards.menu import get_main_menu_kb
    kb = get_main_menu_kb()

    text = (
        "🚀 <b>Starvell Assistant Bot успешно запущен!</b>\n\n"
        "📢 <b>Канал проекта:</b> @starvell_assistant\n"
        "🐙 <b>GitHub:</b> github.com/gadacy/starvell-assistant\n\n"
        "🟢 <b>Все службы активны:</b>\n"
        "• 💬 Живой чат & Пересылка сообщений\n"
        "• ⚡ Автовыдача и автоподнятие лотов\n"
        "• 📉 Демпинг цен и авто-ответчик\n"
        "• ⭐ Напоминалка про отзывы\n\n"
        "👇 <b>Панель управления бота:</b>"
    )

    for admin_id in config.telegram_admin_ids:
        try:
            await bot.send_message(admin_id, text, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)
        except Exception as e:
            logger.error(f"[TelegramBot] Ошибка отправки панели администратору {admin_id}: {e}")

