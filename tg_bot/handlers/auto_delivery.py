from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select, func
from core.database.base import AsyncSessionLocal
from core.database.models import BotSetting, StockItem, OrderHistory
from tg_bot.keyboards.menu import get_back_kb

router = Router()

def get_auto_delivery_kb(is_enabled: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=f"Авто-выдача: {'🟢 ВКЛ' if is_enabled else '🔴 ВЫКЛ'}",
                callback_data="toggle_auto_delivery"
            )
        ],
        [
            InlineKeyboardButton(text="📦 Склад товаров", callback_data="menu_stock"),
            InlineKeyboardButton(text="➕ Добавить ключи", callback_data="stock_add")
        ],
        [
            InlineKeyboardButton(text="◀️ Главное меню", callback_data="menu_main")
        ]
    ])

@router.callback_query(F.data == "menu_auto_delivery")
async def cb_auto_delivery_menu(call: CallbackQuery):
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(BotSetting).where(BotSetting.key == "auto_delivery_enabled"))
        setting = res.scalar_one_or_none()
        is_enabled = setting.value.lower() == "true" if setting else True

        stock_res = await session.execute(
            select(func.count(StockItem.id)).where(StockItem.is_used == False)
        )
        total_stock = stock_res.scalar() or 0

        delivered_res = await session.execute(
            select(func.count(OrderHistory.id)).where(OrderHistory.status == "delivered")
        )
        total_delivered = delivered_res.scalar() or 0

    text = (
        "⚡ **Панель управления Авто-выдачей товаров:**\n\n"
        "Бот автоматически выдает цифровые товары (ключи, аккаунты, промокоды) "
        "покупателю сразу после оплаты заказа на Starvell.com.\n\n"
        f"📊 **Статус модуля:** {'🟢 Включен' if is_enabled else '🔴 Выключен'}\n"
        f"📦 **Доступно товаров на складе:** `{total_stock}` шт.\n"
        f"🎉 **Успешно выдано заказов:** `{total_delivered}` шт."
    )
    await call.message.edit_text(text, reply_markup=get_auto_delivery_kb(is_enabled), parse_mode="Markdown")

@router.callback_query(F.data == "toggle_auto_delivery")
async def cb_toggle_auto_delivery(call: CallbackQuery):
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(BotSetting).where(BotSetting.key == "auto_delivery_enabled"))
        setting = res.scalar_one_or_none()
        if setting:
            setting.value = "false" if setting.value.lower() == "true" else "true"
        else:
            session.add(BotSetting(key="auto_delivery_enabled", value="false"))
        await session.commit()

    # If toggled from settings menu, return to settings menu
    if call.message and call.message.text and "Настройки модулей" in call.message.text:
        from tg_bot.handlers.common import cb_settings
        await cb_settings(call)
    else:
        await cb_auto_delivery_menu(call)
