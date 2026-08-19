from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select
from core.database.base import AsyncSessionLocal
from core.database.models import BotSetting
from core.logger import logger
from tg_bot.keyboards.menu import get_back_kb
from tg_bot.handlers.features import get_client

router = Router()

def get_auto_raise_kb(is_enabled: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=f"Авто-поднятие: {'🟢 ВКЛ' if is_enabled else '🔴 ВЫКЛ'}",
                callback_data="toggle_auto_raise"
            )
        ],
        [
            InlineKeyboardButton(text="🚀 Поднять все лоты СЕЙЧАС", callback_data="auto_raise_now")
        ],
        [
            InlineKeyboardButton(text="◀️ Главное меню", callback_data="menu_main")
        ]
    ])

@router.callback_query(F.data == "menu_auto_raise")
async def cb_auto_raise_menu(call: CallbackQuery):
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(BotSetting).where(BotSetting.key == "auto_raise_enabled"))
        setting = res.scalar_one_or_none()
        is_enabled = setting.value.lower() == "true" if setting else True

    text = (
        "🚀 **Панель Авто-поднятия лотов:**\n\n"
        "Бот каждые 30 минут автоматически отправляет запрос на поднятие ваших лотов в верх списка на Starvell.com.\n\n"
        f"📊 **Статус модуля:** {'🟢 Включен' if is_enabled else '🔴 Выключен'}"
    )
    await call.message.edit_text(text, reply_markup=get_auto_raise_kb(is_enabled), parse_mode="Markdown")

@router.callback_query(F.data == "auto_raise_now")
async def cb_auto_raise_now(call: CallbackQuery):
    await call.answer("🚀 Запускаем поднятие лотов...", show_alert=False)
    
    client = get_client()
    if not client:
        await call.message.answer("⚠️ Клиент Starvell не инициализирован.")
        return

    result = await client.raise_lots()
    if isinstance(result, dict):
        raised_list = result.get("raised", [])
        cooldown_list = result.get("cooldowns", [])
    elif isinstance(result, list):
        raised_list = result
        cooldown_list = []
    else:
        raised_list = []
        cooldown_list = []

    lines = []
    if raised_list:
        lines.append("✅ **Успешно подняты лоты в категориях:**")
        for r in raised_list:
            lines.append(f"• `{r}`")
        lines.append("")

    if cooldown_list:
        lines.append("⏳ **Поднятие лотов пока на кулдауне:**")
        for c in cooldown_list:
            lines.append(f"• `{c}`")
        lines.append("\n💡 *Starvell позволяет поднимать лоты раз в несколько часов.*")

    if not lines:
        lines.append("ℹ️ **Кнопка поднятия пока недоступна** (таймаут от сайта Starvell, попробуйте позже).")

    await call.message.answer(
        "\n".join(lines),
        reply_markup=get_back_kb(),
        parse_mode="Markdown"
    )
