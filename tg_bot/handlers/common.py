import asyncio
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select
from core.database.base import AsyncSessionLocal
from core.database.models import BotSetting
from config import config
from version import __version__
from services.update_checker import UpdateCheckerService
from tg_bot.keyboards.menu import get_main_menu_kb, get_settings_kb, get_notifications_kb, get_back_kb, get_admins_kb, get_admin_delete_kb

router = Router()

class WatermarkState(StatesGroup):
    waiting_for_text = State()

class AdminManagementState(StatesGroup):
    waiting_for_admin_id = State()

def is_admin(user_id: int) -> bool:
    return user_id in config.telegram_admin_ids

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Доступ запрещен. Вы не являетесь администратором бота.")
        return

    await state.clear()
    welcome_text = (
        f"👑 <b>Starvell Assistant Bot</b> (v{__version__})\n\n"
        "💬 <b>Чат проекта:</b> @StarAssis\n"
        "📢 <b>Канал проекта:</b> @starvell_assistant\n"
        "🧩 <b>Плагины:</b> @StarPlugin\n"
        "📁 <b>Папка чатов:</b> https://t.me/addlist/QmOelFMfLqE0MWEy\n"
        "🐙 <b>GitHub:</b> github.com/gadacy/starvell-assistant\n\n"
        "Бот успешно запущен и готов к работе.\n"
        "Используйте меню ниже для управления авто-ответом, авто-выдачей, лотами и просмотра статистики."
    )
    await message.answer(welcome_text, reply_markup=get_main_menu_kb(), parse_mode="HTML", disable_web_page_preview=True)

@router.message(Command("restart"))
async def cmd_restart(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Доступ запрещен.")
        return

    await message.answer(
        "🔄 <b>Выполняется системный перезапуск процесса бота...</b>",
        parse_mode="HTML"
    )
    await asyncio.sleep(1.0)
    UpdateCheckerService.restart_bot()

@router.callback_query(F.data == "menu_main")
async def cb_main_menu(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await state.clear()
    await call.message.edit_text(
        f"👑 <b>Главное меню управления Starvell Assistant (v{__version__}):</b>",
        reply_markup=get_main_menu_kb(),
        parse_mode="HTML"
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
        f"⚙️ <b>Настройки модулей бота:</b>\n\n"
        f"🤖 <b>Водяной знак авто-сообщений:</b>\n<code>{wm_text}</code>\n\n"
        f"Нажмите на кнопку для изменения настроек.",
        reply_markup=get_settings_kb(responder, delivery, raise_lots, watermark),
        parse_mode="HTML"
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

    if call.data == "toggle_auto_delivery":
        from tg_bot.handlers.auto_delivery import cb_auto_delivery_menu
        await cb_auto_delivery_menu(call)
    elif call.data == "toggle_auto_raise":
        from tg_bot.handlers.auto_raise import cb_auto_raise_menu
        await cb_auto_raise_menu(call)
    else:
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
        "✏️ <b>Введите новый текст водяного знака для авто-сообщений бота:</b>\n\n"
        "Пример: <code>🤖 Отправлено через Starvell Assistant</code>",
        reply_markup=get_back_kb(),
        parse_mode="HTML"
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
        f"✅ <b>Водяной знак успешно обновлен!</b>\n\n<code>{new_text}</code>",
        reply_markup=get_back_kb(),
        parse_mode="HTML"
    )

# --- Admins / Access Management ---
@router.message(Command("admins"))
@router.callback_query(F.data == "menu_admins")
async def handle_admins_menu(event: Message | CallbackQuery, state: FSMContext = None):
    user_id = event.from_user.id
    if not is_admin(user_id):
        return

    if state:
        await state.clear()

    admin_ids = config.telegram_admin_ids
    lines = []
    for idx, aid in enumerate(admin_ids, 1):
        suffix = " 👑 (Вы)" if aid == user_id else ""
        lines.append(f"{idx}. <code>{aid}</code>{suffix}")

    admins_str = "\n".join(lines) if lines else "<i>Список пуст</i>"
    text = (
        "👥 <b>Управление администраторами и доступом:</b>\n\n"
        f"<b>Авторизованные Telegram ID ({len(admin_ids)}):</b>\n{admins_str}\n\n"
        "💡 Все пользователи из этого списка имеют доступ к панели управления ботом и получают уведомления о заказах и сообщениях.\n\n"
        "<i>Быстрые команды:</i>\n"
        "• <code>/add_admin &lt;id&gt;</code> — добавить пользователя\n"
        "• <code>/del_admin &lt;id&gt;</code> — удалить пользователя"
    )

    kb = get_admins_kb(admin_ids)
    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await event.answer(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "admin_add")
async def cb_admin_add(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return

    await state.set_state(AdminManagementState.waiting_for_admin_id)
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="menu_admins")]
    ])
    await call.message.edit_text(
        "➕ <b>Добавление нового пользователя в список доступа:</b>\n\n"
        "Отправьте численное значение <b>Telegram ID</b> пользователя.\n\n"
        "💡 <i>Пользователь может узнать свой ID в Telegram через ботов @userinfobot или @myidbot (только цифры).</i>",
        reply_markup=cancel_kb,
        parse_mode="HTML"
    )

@router.message(AdminManagementState.waiting_for_admin_id)
async def process_add_admin_id(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    text = (message.text or "").strip()
    if not text.isdigit():
        cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="menu_admins")]
        ])
        await message.answer(
            "⚠️ Неверный формат ID. Telegram ID должен состоять только из цифр (например: <code>123456789</code>).\n"
            "Попробуйте отправить ID заново или нажмите кнопку отмены:",
            reply_markup=cancel_kb,
            parse_mode="HTML"
        )
        return

    new_id = int(text)
    if new_id in config.telegram_admin_ids:
        await state.clear()
        await message.answer(
            f"ℹ️ Пользователь с ID <code>{new_id}</code> уже есть в списке доступа.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="👥 Список администраторов", callback_data="menu_admins")]
            ]),
            parse_mode="HTML"
        )
        return

    success = config.add_admin_id(new_id)
    await state.clear()
    if success:
        await message.answer(
            f"✅ <b>Пользователь успешно добавлен!</b>\n\n"
            f"ID <code>{new_id}</code> теперь имеет доступ к управлению ботом и уведомлениям.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="👥 Список администраторов", callback_data="menu_admins")]
            ]),
            parse_mode="HTML"
        )
    else:
        await message.answer("❌ Не удалось добавить пользователя.", reply_markup=get_back_kb())

@router.callback_query(F.data == "admin_remove_list")
async def cb_admin_remove_list(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return

    if len(config.telegram_admin_ids) <= 1:
        await call.answer("⚠️ Нельзя удалить единственного администратора!", show_alert=True)
        return

    kb = get_admin_delete_kb(config.telegram_admin_ids, call.from_user.id)
    await call.message.edit_text(
        "➖ <b>Выберите пользователя для отзыва доступа:</b>\n\n"
        "Нажмите на кнопку с ID пользователя, доступ которого хотите заблокировать:",
        reply_markup=kb,
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("admin_del_"))
async def cb_admin_delete(call: CallbackQuery):
    user_id = call.from_user.id
    if not is_admin(user_id):
        return

    del_id_str = call.data.replace("admin_del_", "")
    if not del_id_str.isdigit():
        return
    del_id = int(del_id_str)

    if len(config.telegram_admin_ids) <= 1:
        await call.answer("⚠️ Нельзя удалить единственного администратора!", show_alert=True)
        return

    success = config.remove_admin_id(del_id)
    if success:
        await call.answer(f"✅ Доступ для ID {del_id} отозван.", show_alert=True)
    else:
        await call.answer("❌ Не удалось найти указанный ID.", show_alert=True)

    await handle_admins_menu(call, None)

@router.message(Command("add_admin"))
async def cmd_add_admin(message: Message):
    if not is_admin(message.from_user.id):
        return

    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].strip().isdigit():
        await message.answer(
            "⚠️ <b>Использование:</b> <code>/add_admin &lt;telegram_id&gt;</code>\n"
            "Пример: <code>/add_admin 123456789</code>",
            parse_mode="HTML"
        )
        return

    new_id = int(parts[1].strip())
    if new_id in config.telegram_admin_ids:
        await message.answer(f"ℹ️ ID <code>{new_id}</code> уже есть в списке доступа.", parse_mode="HTML")
        return

    config.add_admin_id(new_id)
    await message.answer(
        f"✅ Пользователь с ID <code>{new_id}</code> успешно добавлен в список доступа.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👥 Список администраторов", callback_data="menu_admins")]
        ]),
        parse_mode="HTML"
    )

@router.message(Command("del_admin"))
async def cmd_del_admin(message: Message):
    if not is_admin(message.from_user.id):
        return

    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].strip().isdigit():
        await message.answer(
            "⚠️ <b>Использование:</b> <code>/del_admin &lt;telegram_id&gt;</code>\n"
            "Пример: <code>/del_admin 123456789</code>",
            parse_mode="HTML"
        )
        return

    del_id = int(parts[1].strip())
    if len(config.telegram_admin_ids) <= 1:
        await message.answer("⚠️ Нельзя удалить единственного администратора!", parse_mode="HTML")
        return

    if del_id not in config.telegram_admin_ids:
        await message.answer(f"❌ ID <code>{del_id}</code> не найден в списке доступа.", parse_mode="HTML")
        return

    config.remove_admin_id(del_id)
    await message.answer(
        f"✅ Доступ для ID <code>{del_id}</code> успешно отозван.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👥 Список администраторов", callback_data="menu_admins")]
        ]),
        parse_mode="HTML"
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
        "🔔 <b>Настройка уведомлений Telegram (Starvell Assistant):</b>\n\n"
        "Управляйте тем, какие сообщения и оповещения бот будет присылать вам в Telegram.\n"
        "Нажмите на соответствующую кнопку для включения/выключения типа уведомлений."
    )

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await event.answer(text, reply_markup=kb, parse_mode="HTML")

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

# --- Test Purchase Notification ---
@router.message(Command("test_order"))
@router.callback_query(F.data == "test_purchase_notification")
async def handle_test_purchase(event: Message | CallbackQuery):
    user_id = event.from_user.id
    if not is_admin(user_id):
        return

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    import random

    test_id = f"F{random.randint(10, 99)}WQ43K"
    test_uuid = "01a04ef2-c0f3-5640-8cfa-5f0a190a4f13"
    test_buyer = "StarvellBuyer_Demo"
    test_title = "Roblox Аккаунт 2012 Года [VIP / БЕЗ ПРИВЯЗОК]"
    test_price = 150.00
    test_chat_id = "demo_chat_123"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✉️ Ответить", callback_data=f"reply_chat_{test_chat_id}"),
            InlineKeyboardButton(text="📝 Заготовки", callback_data=f"quick_replies_{test_chat_id}")
        ],
        [
            InlineKeyboardButton(text="🌐 Открыть заказ", url=f"https://starvell.com/order/{test_uuid}"),
            InlineKeyboardButton(text="💬 Чат", url=f"https://starvell.com/chat/{test_chat_id}")
        ],
        [
            InlineKeyboardButton(text="💸 Возврат средств", callback_data=f"refund_order_{test_id}")
        ]
    ])

    test_msg = (
        "🧪 <b>[ТЕСТОВОЕ ОПОВЕЩЕНИЕ]</b>\n\n"
        "🛍 <b>Новая покупка на Starvell!</b>\n\n"
        f"📦 <b>Товар:</b> {test_title}\n"
        f"👤 <b>Покупатель:</b> <a href='https://starvell.com/profile/{test_buyer}'>{test_buyer}</a>\n"
        f"💵 <b>Сумма:</b> {test_price:.2f} ₽\n"
        f"🆔 <b>ID Заказа:</b> <code>#{test_id}</code>\n\n"
        "⚡ <b>Авто-выдача:</b> <i>Тестовый заказ. Детекция и отправка уведомлений работают отлично!</i>"
    )

    if isinstance(event, CallbackQuery):
        await event.answer("✅ Тестовое уведомление отправлено!", show_alert=False)
        await event.message.answer(test_msg, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)
    else:
        await event.answer(test_msg, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)

# --- Test Review Notification ---
@router.message(Command("test_review"))
@router.callback_query(F.data == "test_review_notification")
async def handle_test_review(event: Message | CallbackQuery):
    user_id = event.from_user.id
    if not is_admin(user_id):
        return

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    import random

    test_short_id = f"F{random.randint(10, 99)}WQ43K"
    test_uuid = "01a04ef2-c0f3-5640-8cfa-5f0a190a4f13"
    test_buyer = "HappyCustomer"
    test_title = "Roblox - Аккаунты (2012 год с войсом)"
    test_comment = "Всё отлично, моментальный ответ, товар полностью рабочий! Рекомендую продавца 👍"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🌐 Открыть заказ", url=f"https://starvell.com/order/{test_uuid}"),
            InlineKeyboardButton(text="💬 Чат", url="https://starvell.com/chat")
        ],
        [
            InlineKeyboardButton(text="👤 Профиль покупателя", url=f"https://starvell.com/profile/{test_buyer}")
        ]
    ])

    test_msg = (
        "🧪 <b>[ТЕСТОВОЕ ОПОВЕЩЕНИЕ]</b>\n\n"
        "⭐ <b>Новый отзыв на Starvell!</b>\n\n"
        "⭐️ <b>Оценка:</b> ⭐⭐⭐⭐⭐ (5/5)\n"
        f"💬 <b>Отзыв:</b> «<i>{test_comment}</i>»\n"
        f"📦 <b>Товар:</b> {test_title}\n"
        f"👤 <b>Покупатель:</b> <a href='https://starvell.com/profile/{test_buyer}'>{test_buyer}</a>\n"
        f"🆔 <b>Заказ:</b> <code>#{test_short_id}</code>"
    )

    if isinstance(event, CallbackQuery):
        await event.answer("✅ Тестовый отзыв отправлен!", show_alert=False)
        await event.message.answer(test_msg, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)
    else:
        await event.answer(test_msg, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)

# --- Update Checker & Self-Restart Handlers ---

@router.callback_query(F.data == "menu_check_updates")
async def cb_check_updates(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return

    await call.message.edit_text("⏳ <b>Проверка наличия обновлений на GitHub...</b>", parse_mode="HTML")
    has_update, msg_text, update_info = await UpdateCheckerService.check_for_updates()

    # Convert markdown to html tags if present in msg_text
    html_msg = msg_text.replace("**", "<b>").replace("`", "<code>")

    buttons = [
        [InlineKeyboardButton(text="🚀 Обновить и перезапустить", callback_data="perform_bot_update")],
        [InlineKeyboardButton(text="◀️ Назад в настройки", callback_data="menu_settings")]
    ]

    await call.message.edit_text(
        html_msg,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
        disable_web_page_preview=True
    )

@router.callback_query(F.data == "perform_bot_update")
async def cb_perform_update(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return

    await call.message.edit_text(
        "⏳ <b>Выполняется скачивание обновлений из GitHub (<code>git pull origin main</code>)...</b>",
        parse_mode="HTML"
    )

    success, result = await UpdateCheckerService.perform_git_pull()
    if success:
        await call.message.edit_text(
            f"✅ <b>Обновление успешно загружено!</b>\n\n<code>{result[:200]}</code>\n\n"
            f"🔄 <b>Выполняется перезапуск процесса бота...</b>",
            parse_mode="HTML"
        )
        await asyncio.sleep(1.0)
        UpdateCheckerService.restart_bot()
    else:
        await call.message.edit_text(
            f"❌ <b>Ошибка при обновлении через Git:</b>\n\n<code>{result}</code>",
            reply_markup=get_back_kb(),
            parse_mode="HTML"
        )
