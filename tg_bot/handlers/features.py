from typing import Optional, List, Dict, Any
from aiogram import Router, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select
from core.database.base import AsyncSessionLocal
from core.database.models import BotSetting, OrderHistory, QuickReply
from core.logger import logger
from starvell.client import StarvellClient
from tg_bot.keyboards.menu import get_back_kb
from tg_bot.handlers.common import is_admin

router = Router()
starvell_client_ref: Optional[StarvellClient] = None

def set_client(client: StarvellClient):
    global starvell_client_ref
    starvell_client_ref = client

def get_client() -> Optional[StarvellClient]:
    return starvell_client_ref

class ReplyState(StatesGroup):
    waiting_for_text = State()

class BroadcastState(StatesGroup):
    waiting_for_text = State()

class GreetingEditState(StatesGroup):
    waiting_for_text = State()

class AddQuickReplyState(StatesGroup):
    waiting_for_title = State()
    waiting_for_text = State()

# --- Main Features Keyboard ---
def get_features_kb(greeting: bool, reminder: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👤 Профиль Starvell", callback_data="feature_profile"),
            InlineKeyboardButton(text="💬 Активные чаты", callback_data="feature_chats")
        ],
        [
            InlineKeyboardButton(text="⚡ Быстрые ответы", callback_data="menu_quick_replies"),
            InlineKeyboardButton(text="📣 Рассылка покупателям", callback_data="feature_broadcast")
        ],
        [
            InlineKeyboardButton(
                text=f"Приветствие: {'🟢 ВКЛ' if greeting else '🔴 ВЫКЛ'}",
                callback_data="toggle_feature_greeting"
            ),
            InlineKeyboardButton(text="✏️ Изменить текст", callback_data="edit_feature_greeting")
        ],
        [
            InlineKeyboardButton(
                text=f"Напоминалка отзывов: {'🟢 ВКЛ' if reminder else '🔴 ВЫКЛ'}",
                callback_data="toggle_feature_reminder"
            )
        ],
        [
            InlineKeyboardButton(text="◀️ Главное меню", callback_data="menu_main")
        ]
    ])

@router.callback_query(F.data == "menu_features")
async def cb_features_menu(call: CallbackQuery):
    async with AsyncSessionLocal() as session:
        res_g = await session.execute(select(BotSetting).where(BotSetting.key == "auto_greeting_enabled"))
        set_g = res_g.scalar_one_or_none()
        greeting = set_g.value.lower() == "true" if set_g else True

        res_r = await session.execute(select(BotSetting).where(BotSetting.key == "review_reminder_enabled"))
        set_r = res_r.scalar_one_or_none()
        reminder = set_r.value.lower() == "true" if set_r else True

    await call.message.edit_text(
        "🎉 **Фишки и Приколюхи Starvell Assistant:**\n\n"
        "Управляйте живыми чатами, автоматическими приветствиями, напоминанием про отзывы и рассылкой!",
        reply_markup=get_features_kb(greeting, reminder),
        parse_mode="Markdown"
    )

# --- 1. Profile Command & Callback ---
@router.message(Command("profile"))
@router.callback_query(F.data == "feature_profile")
async def handle_profile(event: Message | CallbackQuery):
    message = event if isinstance(event, Message) else event.message
    
    client = get_client()
    if not client:
        await message.answer("⚠️ Клиент Starvell еще не инициализирован.")
        return

    profile = await client.get_profile()
    
    text = (
        "👤 **Статистика и Профиль Starvell:**\n\n"
        f"🆔 **ID:** `{profile.id}`\n"
        f"👑 **Никнейм:** **{profile.username}**\n"
        f"🟢 **Статус:** {'Онлайн' if profile.is_online else 'Офлайн'}\n"
        f"⭐️ **Рейтинг:** {profile.rating:.1f} ({profile.reviews_count} отзывов)\n"
        f"💵 **Доступно к выводу:** **{profile.balance_rub:,.2f} RUB**\n"
        f"🔒 **Средства в холде:** {profile.balance_hold:,.2f} RUB\n"
        f"📦 **Статус торговли:** {'🟢 Активна' if profile.is_selling_enabled else '🔴 Приостановлена'} ({profile.kyc_status})"
    )
    
    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=get_back_kb(), parse_mode="Markdown")
    else:
        await message.answer(text, reply_markup=get_back_kb(), parse_mode="Markdown")

# --- 2. Active Chats Command & Callback ---
@router.message(Command("chats"))
@router.callback_query(F.data == "feature_chats")
async def handle_chats(event: Message | CallbackQuery):
    message = event if isinstance(event, Message) else event.message
    
    client = get_client()
    if not client:
        await message.answer("⚠️ Клиент Starvell еще не инициализирован.")
        return

    profile = await client.get_profile()
    my_user_id = profile.id
    my_public_id = profile.public_id

    chats = await client.get_chats()
    if not chats:
        text = "💬 **Активные чаты Starvell:**\n\nУ вас пока нет активных диалогов на Starvell."
        if isinstance(event, CallbackQuery):
            await event.message.edit_text(text, reply_markup=get_back_kb(), parse_mode="Markdown")
        else:
            await message.answer(text, reply_markup=get_back_kb(), parse_mode="Markdown")
        return

    lines = [f"💬 **Активные чаты Starvell ({len(chats)}):**\n"]
    buttons = []

    for idx, chat in enumerate(chats[:10], 1):
        chat_id = chat.get("id")
        unread = chat.get("unreadMessageCount", 0)
        participants = chat.get("participants", [])

        other_name = "Покупатель"
        for p in participants:
            if isinstance(p, dict):
                p_id = str(p.get("id", ""))
                p_pub = str(p.get("publicId", ""))
                if p_id != str(my_user_id) and (not my_public_id or p_pub != str(my_public_id)):
                    other_name = p.get("username", "Покупатель")
                    break

        last_msg = chat.get("lastMessage", {}) or {}
        msg_text = last_msg.get("content") or last_msg.get("text") or "..."
        unread_badge = f" 🔴 (+{unread})" if unread > 0 else ""

        lines.append(f"{idx}. 👤 **{other_name}**{unread_badge}")
        lines.append(f"   💬 _{msg_text[:40]}_")
        lines.append(f"   ✍️ Ответить: `/reply {chat_id} Ваш текст`\n")

        btn_text = f"💬 Ответить {other_name[:14]}{unread_badge}"
        buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"reply_chat_{chat_id}")])

    buttons.append([InlineKeyboardButton(text="🔄 Обновить список", callback_data="feature_chats")])
    buttons.append([InlineKeyboardButton(text="◀️ Главное меню", callback_data="menu_main")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    text = "\n".join(lines)

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    else:
        await message.answer(text, reply_markup=kb, parse_mode="Markdown")

# --- 3. Reply Command (/reply <chat_id> <text>) ---
@router.message(Command("reply"))
async def cmd_reply(message: Message, command: CommandObject):
    if not command.args:
        await message.answer(
            "✍️ **Использование команды:**\n"
            "`/reply <chat_id> Ваш текст ответа`\n\n"
            "Пример:\n`/reply 019fecd7-6b78-81a3-50da-87c94faec2bb Здравствуйте, ваш товар отправлен!`",
            parse_mode="Markdown"
        )
        return

    parts = command.args.split(" ", 1)
    if len(parts) < 2:
        await message.answer("⚠️ Введите текст сообщения ответа!")
        return

    chat_id, text_to_send = parts[0], parts[1]
    client = get_client()
    if client:
        ok = await client.send_message(chat_id, text_to_send)
        if ok:
            await message.answer(f"✅ **Сообщение успешно отправлено покупателю!** (`{chat_id}`)", parse_mode="Markdown")
        else:
            await message.answer(f"❌ Не удалось отправить сообщение в чат {chat_id}.")
    else:
        await message.answer("⚠️ Клиент Starvell еще не инициализирован.")

# --- 4. Inline Reply Button ---
@router.callback_query(F.data.startswith("reply_chat_"))
async def cb_reply_button(call: CallbackQuery, state: FSMContext):
    chat_id = call.data.replace("reply_chat_", "")
    await state.update_data(reply_chat_id=chat_id)
    await state.set_state(ReplyState.waiting_for_text)
    await call.message.answer(
        f"✍️ **Введите ответ для покупателя** (Чат `{chat_id}`):\n\n"
        f"Просто отправьте текст следующим сообщением в этот чат Telegram.",
        parse_mode="Markdown"
    )

@router.message(ReplyState.waiting_for_text)
async def process_reply_text(message: Message, state: FSMContext):
    data = await state.get_data()
    chat_id = data.get("reply_chat_id")
    text_to_send = message.text.strip()

    if not text_to_send:
        await message.answer("⚠️ Пустой текст. Попробуйте еще раз.")
        return

    client = get_client()
    if client:
        ok = await client.send_message(chat_id, text_to_send)
        if ok:
            await message.answer(f"✅ **Сообщение успешно отправлено в Starvell!** (`{chat_id}`)", parse_mode="Markdown")
        else:
            await message.answer("❌ Ошибка отправки сообщения в Starvell.")
    else:
        await message.answer("⚠️ Клиент Starvell еще не инициализирован.")

    await state.clear()

# --- 5. Toggles ---
@router.callback_query(F.data.startswith("toggle_feature_"))
async def cb_toggle_feature(call: CallbackQuery):
    feature_name = call.data.replace("toggle_feature_", "")
    key = f"auto_{feature_name}_enabled" if feature_name == "greeting" else f"{feature_name}_enabled"

    async with AsyncSessionLocal() as session:
        res = await session.execute(select(BotSetting).where(BotSetting.key == key))
        setting = res.scalar_one_or_none()
        if setting:
            setting.value = "false" if setting.value.lower() == "true" else "true"
        else:
            session.add(BotSetting(key=key, value="false"))
        await session.commit()

    await cb_features_menu(call)

# --- 6. Broadcast ---
@router.callback_query(F.data == "feature_broadcast")
async def cb_broadcast(call: CallbackQuery, state: FSMContext):
    await state.set_state(BroadcastState.waiting_for_text)
    await call.message.edit_text(
        "📣 **Массовая рассылка всем покупателям Starvell:**\n\n"
        "Введите текст сообщения для рассылки всем клиентам из вашей истории заказов.",
        reply_markup=get_back_kb(),
        parse_mode="Markdown"
    )

@router.message(BroadcastState.waiting_for_text)
async def process_broadcast_text(message: Message, state: FSMContext):
    text_to_broadcast = message.text.strip()
    if not text_to_broadcast:
        await message.answer("⚠️ Пустой текст рассылки.")
        return

    async with AsyncSessionLocal() as session:
        res = await session.execute(select(OrderHistory.buyer_id).distinct())
        buyer_ids = [r[0] for r in res.all() if r[0]]

    sent_count = 0
    client = get_client()
    if client and buyer_ids:
        for b_id in buyer_ids:
            try:
                ok = await client.send_message(b_id, text_to_broadcast)
                if ok:
                    sent_count += 1
            except Exception:
                pass

    await state.clear()
    await message.answer(
        f"🎉 **Рассылка завершена!** Сообщение доставлено `{sent_count}` покупателям.",
        reply_markup=get_back_kb(),
        parse_mode="Markdown"
    )

# --- 6. Edit Greeting Message ---
@router.callback_query(F.data == "edit_feature_greeting")
async def cb_edit_greeting(call: CallbackQuery, state: FSMContext):
    await state.set_state(GreetingEditState.waiting_for_text)
    await call.message.edit_text(
        "✏️ **Редактирование приветственного сообщения:**\n\n"
        "Введите новый текст приветствия.\n"
        "💡 *Вы можете использовать макрос* `{buyer_name}` *для имени покупателя.*\n\n"
        "Пример:\n"
        "`👋 Здравствуйте, {buyer_name}! Рады видеть вас в магазине. Чем могу помочь?`",
        reply_markup=get_back_kb(),
        parse_mode="Markdown"
    )

@router.message(GreetingEditState.waiting_for_text)
async def process_new_greeting(message: Message, state: FSMContext):
    new_text = message.text.strip()
    if not new_text:
        await message.answer("⚠️ Текст приветствия не может быть пустым.")
        return

    async with AsyncSessionLocal() as session:
        res = await session.execute(select(BotSetting).where(BotSetting.key == "auto_greeting_text"))
        setting = res.scalar_one_or_none()
        if setting:
            setting.value = new_text
        else:
            session.add(BotSetting(key="auto_greeting_text", value=new_text))
        await session.commit()

    await state.clear()
    await message.answer(
        f"✅ **Приветственное сообщение успешно сохранено!**\n\n`{new_text}`",
        reply_markup=get_back_kb(),
        parse_mode="Markdown"
    )

# --- 7. Quick Replies for Chat Notification ---
@router.callback_query(F.data.startswith("quick_replies_"))
async def cb_quick_replies_for_chat(call: CallbackQuery):
    chat_id = call.data.replace("quick_replies_", "")
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(QuickReply).order_by(QuickReply.id))
        qrs = res.scalars().all()

    if not qrs:
        await call.message.answer(
            "⚠️ У вас пока нет созданных быстрых ответов!\n"
            "Создать их можно в меню: **Фишки & Чат -> ⚡ Быстрые ответы**.",
            reply_markup=get_back_kb(),
            parse_mode="Markdown"
        )
        return

    buttons = []
    for qr in qrs:
        buttons.append([
            InlineKeyboardButton(
                text=f"⚡ {qr.title}",
                callback_data=f"send_qr_{qr.id}_{chat_id}"
            )
        ])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu_main")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await call.message.answer(
        f"⚡ **Выберите быстрый ответ для чата** (`{chat_id[:8]}...`):",
        reply_markup=kb,
        parse_mode="Markdown"
    )

@router.callback_query(F.data.startswith("send_qr_"))
async def cb_send_quick_reply(call: CallbackQuery):
    parts = call.data.split("_")
    if len(parts) < 4:
        return
    qr_id = int(parts[2])
    chat_id = "_".join(parts[3:])

    async with AsyncSessionLocal() as session:
        res = await session.execute(select(QuickReply).where(QuickReply.id == qr_id))
        qr = res.scalar_one_or_none()

    if not qr:
        await call.answer("❌ Быстрый ответ не найден.", show_alert=True)
        return

    client = get_client()
    if not client:
        await call.answer("⚠️ Клиент Starvell не инициализирован.", show_alert=True)
        return

    ok = await client.send_message(chat_id, qr.text)
    if ok:
        await call.answer(f"✅ Быстрый ответ «{qr.title}» отправлен!", show_alert=True)
        await call.message.answer(
            f"✅ **Быстрый ответ «{qr.title}» успешно отправлен в Starvell!**\n\n💬 `{qr.text}`",
            reply_markup=get_back_kb(),
            parse_mode="Markdown"
        )
    else:
        await call.answer("❌ Ошибка отправки в Starvell.", show_alert=True)

# --- 8. Quick Replies Management Menu ---
@router.message(Command("quick_replies"))
@router.message(Command("qr"))
@router.callback_query(F.data == "menu_quick_replies")
async def handle_quick_replies_menu(event: Message | CallbackQuery):
    message = event if isinstance(event, Message) else event.message
    
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(QuickReply).order_by(QuickReply.id))
        qrs = res.scalars().all()

    lines = ["⚡ **Управление быстрыми ответами Starvell:**\n"]
    if qrs:
        for idx, qr in enumerate(qrs, 1):
            lines.append(f"{idx}. **{qr.title}**")
            lines.append(f"   💬 _{qr.text[:60]}_\n")
    else:
        lines.append("У вас пока нет сохраненных быстрых ответов.\n")

    buttons = [
        [
            InlineKeyboardButton(text="➕ Добавить ответ", callback_data="qr_add"),
            InlineKeyboardButton(text="🗑 Удалить ответ", callback_data="qr_delete_menu")
        ],
        [
            InlineKeyboardButton(text="◀️ Назад в меню", callback_data="menu_features")
        ]
    ]

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    text = "\n".join(lines)

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    else:
        await message.answer(text, reply_markup=kb, parse_mode="Markdown")

@router.callback_query(F.data == "qr_add")
async def cb_qr_add_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(AddQuickReplyState.waiting_for_title)
    await call.message.edit_text(
        "✍️ **Создание быстрого ответа (Шаг 1 из 2):**\n\n"
        "Введите короткое название для кнопки (например: `👋 Приветствие`, `✅ Товар отправлен`, `⭐ Отзыв`):",
        reply_markup=get_back_kb(),
        parse_mode="Markdown"
    )

@router.message(AddQuickReplyState.waiting_for_title)
async def process_qr_title(message: Message, state: FSMContext):
    title = message.text.strip()
    if not title:
        await message.answer("⚠️ Название не может быть пустым.")
        return
    await state.update_data(qr_title=title)
    await state.set_state(AddQuickReplyState.waiting_for_text)
    await message.answer(
        f"✍️ **Создание быстрого ответа (Шаг 2 из 2):**\n\n"
        f"Название: **{title}**\n\n"
        f"Теперь введите полный текст сообщения, который будет отправляться покупателю в Starvell:",
        parse_mode="Markdown"
    )

@router.message(AddQuickReplyState.waiting_for_text)
async def process_qr_text(message: Message, state: FSMContext):
    qr_text = message.text.strip()
    if not qr_text:
        await message.answer("⚠️ Текст ответа не может быть пустым.")
        return

    data = await state.get_data()
    title = data.get("qr_title", "Быстрый ответ")

    async with AsyncSessionLocal() as session:
        qr = QuickReply(title=title, text=qr_text)
        session.add(qr)
        await session.commit()

    await state.clear()
    await message.answer(
        f"✅ **Быстрый ответ «{title}» успешно сохранен!**\n\n💬 `{qr_text}`",
        reply_markup=get_back_kb(),
        parse_mode="Markdown"
    )

@router.callback_query(F.data == "qr_delete_menu")
async def cb_qr_delete_menu(call: CallbackQuery):
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(QuickReply).order_by(QuickReply.id))
        qrs = res.scalars().all()

    if not qrs:
        await call.answer("У вас нет быстрых ответов для удаления.", show_alert=True)
        return

    buttons = []
    for qr in qrs:
        buttons.append([
            InlineKeyboardButton(
                text=f"❌ Удалить: {qr.title}",
                callback_data=f"qr_del_{qr.id}"
            )
        ])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu_quick_replies")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await call.message.edit_text(
        "🗑 **Выберите быстрый ответ для удаления:**",
        reply_markup=kb,
        parse_mode="Markdown"
    )

@router.callback_query(F.data.startswith("qr_del_"))
async def cb_qr_delete(call: CallbackQuery):
    qr_id = int(call.data.replace("qr_del_", ""))
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(QuickReply).where(QuickReply.id == qr_id))
        qr = res.scalar_one_or_none()
        if qr:
            title = qr.title
            await session.delete(qr)
            await session.commit()
            await call.answer(f"🗑 Быстрый ответ «{title}» удален!", show_alert=True)
        else:
            await call.answer("❌ Ответ не найден.", show_alert=True)

    await handle_quick_replies_menu(call)

@router.callback_query(F.data.startswith("refund_order_"))
async def cb_refund_order(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    order_id = call.data.replace("refund_order_", "")
    await call.answer(
        f"ℹ️ Для выполнения возврата по заказу #{order_id} перейдите на страницу заказа на Starvell.com.",
        show_alert=True
    )
