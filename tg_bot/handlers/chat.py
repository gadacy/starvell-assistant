import html

from aiogram import F, Router
from aiogram.filters import Command, Filter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from core.logger import logger
from services.chat_state import get_reply_target, save_reply_target

router = Router()


class ChatReplyState(StatesGroup):
    active = State()


class LinkedChatReply(Filter):
    async def __call__(self, message: Message):
        if not message.reply_to_message or (message.text or "").startswith("/"):
            return False
        chat_id = await get_reply_target(message.chat.id, message.reply_to_message.message_id)
        return {"starvell_chat_id": chat_id} if chat_id else False


def close_chat_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✖️ Закрыть переписку", callback_data="close_starvell_chat")
    ]])


async def send_chat_reply(message: Message, starvell_chat_id: str, text: str = None) -> bool:
    from tg_bot.handlers.features import get_client

    text = (text if text is not None else message.text or "").strip()
    if not text:
        await message.answer("Отправьте текстовое сообщение. Фото, файлы и голосовые пока не поддерживаются.")
        return False
    client = get_client()
    if not client:
        await message.answer("⚠️ Клиент Starvell еще не инициализирован. Попробуйте позже.")
        return False
    try:
        sent_ok = await client.send_message(starvell_chat_id, text)
    except Exception as exc:
        logger.error(f"[TelegramChat] Sending to chat {starvell_chat_id} failed: {exc}")
        sent_ok = False
    if not sent_ok:
        await message.answer("❌ Starvell не подтвердил отправку. Проверьте чат перед повторной попыткой.")
        return False

    receipt = await message.answer(
        f"✅ Отправлено в чат <code>{html.escape(starvell_chat_id)}</code>.\n"
        "На это сообщение тоже можно ответить через Telegram.",
        parse_mode="HTML",
    )
    try:
        await save_reply_target(receipt.chat.id, receipt.message_id, starvell_chat_id)
    except Exception as exc:
        logger.error(f"[TelegramChat] Could not save reply receipt: {exc}")
    return True


# Exact Telegram replies take precedence over a previously selected chat or another form.
@router.message(LinkedChatReply())
async def reply_to_notification(message: Message, starvell_chat_id: str, state: FSMContext):
    if await state.get_state() == ChatReplyState.active.state:
        if (await state.get_data()).get("starvell_chat_id") != starvell_chat_id:
            await state.clear()
    await send_chat_reply(message, starvell_chat_id)


@router.callback_query(F.data.startswith("reply_chat_"))
async def open_chat(call: CallbackQuery, state: FSMContext):
    chat_id = call.data.removeprefix("reply_chat_").strip()
    if not chat_id or not call.message:
        await call.answer("Чат не найден.", show_alert=True)
        return
    await call.answer()
    await state.clear()
    prompt = await call.message.answer(
        f"✍️ Открыта переписка с чатом <code>{html.escape(chat_id)}</code>.\n\n"
        "Следующие текстовые сообщения будут отправляться этому покупателю. "
        "Можно написать несколько сообщений подряд.\n"
        "Чтобы закончить, нажмите «Закрыть переписку» или отправьте /cancel.",
        parse_mode="HTML", reply_markup=close_chat_keyboard(),
    )
    await save_reply_target(prompt.chat.id, prompt.message_id, chat_id)
    await state.set_state(ChatReplyState.active)
    await state.update_data(starvell_chat_id=chat_id)


@router.message(ChatReplyState.active, Command("cancel"))
async def cancel_chat(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Переписка закрыта. Новые сообщения не будут отправляться покупателю.")


@router.callback_query(F.data == "close_starvell_chat")
async def close_chat(call: CallbackQuery, state: FSMContext):
    if await state.get_state() == ChatReplyState.active.state:
        await state.clear()
    await call.answer("Переписка закрыта.")
    if call.message:
        await call.message.edit_reply_markup(reply_markup=None)


@router.message(ChatReplyState.active, ~F.text.startswith("/"))
async def send_to_active_chat(message: Message, state: FSMContext):
    if message.reply_to_message:
        await message.answer("Не удалось определить чат по этому сообщению. Ответьте на уведомление Starvell или выберите покупателя кнопкой «Ответить».")
        return
    chat_id = (await state.get_data()).get("starvell_chat_id")
    if not chat_id:
        await state.clear()
        await message.answer("Выберите покупателя кнопкой «Ответить».")
        return
    await send_chat_reply(message, chat_id)
