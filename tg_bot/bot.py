import asyncio
from typing import Optional
from aiogram import Bot, Dispatcher
from config import config
from core.logger import logger
from tg_bot.handlers import common, stock, auto_response, stats, features, dumper, auto_raise, plugins

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

    # Register routers
    dp.include_router(common.router)
    dp.include_router(stock.router)
    dp.include_router(auto_response.router)
    dp.include_router(stats.router)
    dp.include_router(features.router)
    dp.include_router(dumper.router)
    dp.include_router(auto_raise.router)
    dp.include_router(plugins.router)

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

async def send_admin_startup_panel():
    if not bot or not config.telegram_admin_ids:
        return

    from tg_bot.keyboards.menu import get_main_menu_kb
    kb = get_main_menu_kb()

    text = (
        "🚀 <b>Starvell Assistant Bot успешно запущен!</b>\n\n"
        "📢 <b>Официальный канал:</b> @starvell_assistant (https://t.me/starvell_assistant)\n\n"
        "🟢 <b>Все службы активны:</b>\n"
        "• 💬 Живой чат & Пересылка сообщений\n"
        "• ⚡ Автовыдача и автоподнятие лотов\n"
        "• 📉 Демпинг цен и авто-ответчик\n"
        "• ⭐ Напоминалка про отзывы\n\n"
        "👇 <b>Панель управления бота:</b>"
    )

    for admin_id in config.telegram_admin_ids:
        try:
            await bot.send_message(admin_id, text, reply_markup=kb, parse_mode="HTML")
        except Exception as e:
            logger.error(f"[TelegramBot] Ошибка отправки панели администратору {admin_id}: {e}")

