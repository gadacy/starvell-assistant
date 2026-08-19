from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select
from core.database.base import AsyncSessionLocal
from core.database.models import BotSetting
from config import config
from tg_bot.keyboards.menu import get_main_menu_kb, get_settings_kb, get_notifications_kb, get_back_kb

router = Router()

class WatermarkState(StatesGroup):
    waiting_for_text = State()

def is_admin(user_id: int) -> bool:
    if not config.telegram_admin_ids:
        return True  # If no admin set, allow first user
    return user_id in config.telegram_admin_ids

@router.message(Command("start"))
async def cmd_start(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Доступ запрещен. Вы не являетесь администратором бота.")
        return

    welcome_text = (
        "👑 **Добро пожаловать в Starvell Assistant Bot!**\n\n"
        "📢 **Официальный канал проекта:** [@starvell_assistant](https://t.me/starvell_assistant)\n\n"
        "Бот успешно запущен и готов к работе.\n"
        "Используйте меню ниже для управления авто-ответом, авто-выдачей, лотами и просмотра статистики."
    )
    await message.answer(welcome_text, reply_markup=get_main_menu_kb(), parse_mode="Markdown")

@router.callback_query(F.data == "menu_main")
async def cb_main_menu(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    await call.message.edit_text(
        "👑 **Главное меню управления Starvell Assistant:**",
        reply_markup=get_main_menu_kb(),
        parse_mode="Markdown"
    )

# --- Settings Menu ---
@router.callback_query(F.data == "menu_settings")
async def cb_settings(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return

    async with AsyncSessionLocal() as session:
        res = await session.execute(select(BotSetting))
        settings_dict = {s.key: s.value for s in res.scalars().all()}

    responder = settings_dict.get("auto_responder_enabled", "true").lower() == "true"
    delivery = settings_dict.get("auto_delivery_enabled", "true").lower() == "true"
    raise_lots = settings_dict.get("auto_raise_enabled", "true").lower() == "true"
    watermark = settings_dict.get("watermark_enabled", str(config.watermark_enabled)).lower() == "true"

    wm_text = settings_dict.get("watermark_text", config.watermark_text)

    await call.message.edit_text(
        f"⚙️ **Настройки модулей бота:**\n\n"
        f"🤖 **Водяной знак авто-сообщений:**\n`{wm_text}`\n\n"
        f"Нажмите на кнопку для изменения настроек.",
        reply_markup=get_settings_kb(responder, delivery, raise_lots, watermark),
        parse_mode="Markdown"
    )

@router.callback_query(F.data.in_(["toggle_auto_responder", "toggle_auto_delivery", "toggle_auto_raise"]))
async def cb_toggle_setting(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return

    key_map = {
        "toggle_auto_responder": "auto_responder_enabled",
        "toggle_auto_delivery": "auto_delivery_enabled",
        "toggle_auto_raise": "auto_raise_enabled",
    }
    setting_key = key_map.get(call.data, "")
    if not setting_key:
        return

    async with AsyncSessionLocal() as session:
        res = await session.execute(select(BotSetting).where(BotSetting.key == setting_key))
        setting = res.scalar_one_or_none()
        if setting:
            setting.value = "false" if setting.value.lower() == "true" else "true"
        else:
            session.add(BotSetting(key=setting_key, value="false"))
        await session.commit()

    await cb_settings(call)

@router.callback_query(F.data == "toggle_watermark_enabled")
async def cb_toggle_watermark(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return

    async with AsyncSessionLocal() as session:
        res = await session.execute(select(BotSetting).where(BotSetting.key == "watermark_enabled"))
        setting = res.scalar_one_or_none()
        if setting:
            setting.value = "false" if setting.value.lower() == "true" else "true"
        else:
            session.add(BotSetting(key="watermark_enabled", value="false"))
        await session.commit()

    await cb_settings(call)

@router.callback_query(F.data == "edit_watermark_text")
async def cb_edit_watermark(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return

    await state.set_state(WatermarkState.waiting_for_text)
    await call.message.edit_text(
        "✏️ **Введите новый текст водяного знака для авто-сообщений бота:**\n\n"
        "Пример: `🤖 Отправлено через Starvell Assistant`",
        reply_markup=get_back_kb(),
        parse_mode="Markdown"
    )

@router.message(WatermarkState.waiting_for_text)
async def process_watermark_text(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    new_text = message.text.strip()
    if not new_text:
        await message.answer("⚠️ Текст не может быть пустым.")
        return

    async with AsyncSessionLocal() as session:
        res = await session.execute(select(BotSetting).where(BotSetting.key == "watermark_text"))
        setting = res.scalar_one_or_none()
        if setting:
            setting.value = new_text
        else:
            session.add(BotSetting(key="watermark_text", value=new_text))
        await session.commit()

    await state.clear()
    await message.answer(
        f"✅ **Водяной знак успешно обновлен!**\n\n`{new_text}`",
        reply_markup=get_back_kb(),
        parse_mode="Markdown"
    )

# --- Notifications Settings Panel ---
@router.message(Command("notifications"))
@router.callback_query(F.data == "menu_notifications")
async def handle_notifications_menu(event: Message | CallbackQuery):
    user_id = event.from_user.id if isinstance(event, Message) else event.from_user.id
    if not is_admin(user_id):
        return

    async with AsyncSessionLocal() as session:
        res = await session.execute(select(BotSetting))
        settings_dict = {}
        for s in res.scalars().all():
            settings_dict[s.key] = s.value.lower() == "true"

    defaults = {
        "notify_chat_messages": True,
        "notify_new_orders": True,
        "notify_order_delivery": True,
        "notify_reviews": True,
        "notify_auto_raise": True,
        "notify_dumper": True
    }
    for k, v in defaults.items():
        if k not in settings_dict:
            settings_dict[k] = v

    kb = get_notifications_kb(settings_dict)
    text = (
        "🔔 **Настройка уведомлений Telegram (Starvell Assistant):**\n\n"
        "Управляйте тем, какие сообщения и оповещения бот будет присылать вам в Telegram.\n"
        "Нажмите на соответствующую кнопку для включения/выключения типа уведомлений."
    )

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    else:
        await event.answer(text, reply_markup=kb, parse_mode="Markdown")

@router.callback_query(F.data.startswith("toggle_notify_"))
async def cb_toggle_notify(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return

    key = call.data.replace("toggle_", "")
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(BotSetting).where(BotSetting.key == key))
        setting = res.scalar_one_or_none()
        if setting:
            setting.value = "false" if setting.value.lower() == "true" else "true"
        else:
            session.add(BotSetting(key=key, value="false"))
        await session.commit()

    await handle_notifications_menu(call)
