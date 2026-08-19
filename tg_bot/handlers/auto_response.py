from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select, delete
from core.database.base import AsyncSessionLocal
from core.database.models import AutoResponse
from tg_bot.keyboards.menu import get_back_kb

router = Router()

class AddRuleState(StatesGroup):
    title = State()
    pattern = State()
    response_text = State()

def get_auto_response_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➕ Добавить правило", callback_data="ar_add_rule"),
            InlineKeyboardButton(text="💡 Макросы", callback_data="ar_show_macros")
        ],
        [
            InlineKeyboardButton(text="📋 Список правил", callback_data="ar_list_rules")
        ],
        [
            InlineKeyboardButton(text="◀️ Главное меню", callback_data="menu_main")
        ]
    ])

@router.callback_query(F.data == "menu_auto_response")
async def cb_auto_response_menu(call: CallbackQuery):
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(AutoResponse))
        rules = res.scalars().all()

    text = (
        "🤖 **Панель Авто-ответчика:**\n\n"
        "Бот автоматически распознает сообщения покупателей и отвечает по заготовленным правилам с использованием динамических макросов.\n\n"
        f"📊 **Активных правил:** `{len(rules)}`"
    )
    await call.message.edit_text(text, reply_markup=get_auto_response_kb(), parse_mode="Markdown")

@router.callback_query(F.data == "ar_show_macros")
async def cb_show_macros(call: CallbackQuery):
    text = (
        "💡 **Полный список доступных макросов:**\n\n"
        "• `{buyer_name}` — Имя покупателя на Starvell\n"
        "• `{buyer_id}` — Уникальный ID покупателя\n"
        "• `{order_id}` — ID оформленного заказа\n"
        "• `{lot_name}` — Название купленного товара/лота\n"
        "• `{price}` — Сумма заказа в рублях\n"
        "• `{stock_count}` — Остаток доступных товаров на складе\n"
        "• `{time}` — Текущее время (ЧЧ:ММ:СС)\n"
        "• `{date}` — Текущая дата (ГГГГ-ММ-ДД)\n\n"
        "*Пример использования в ответе:*\n"
        "`Здравствуйте, {buyer_name}! Ваш заказ #{order_id} принят. Остаток на складе: {stock_count} шт.`"
    )
    await call.message.edit_text(text, reply_markup=get_back_kb(), parse_mode="Markdown")

@router.callback_query(F.data == "ar_list_rules")
async def cb_list_rules(call: CallbackQuery):
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(AutoResponse))
        rules = res.scalars().all()

    if not rules:
        await call.message.edit_text(
            "📋 **Правила авто-ответчика отсутствуют.**\nНажмите 'Добавить правило', чтобы создать первое правило.",
            reply_markup=get_back_kb(),
            parse_mode="Markdown"
        )
        return

    buttons = []
    for r in rules:
        status_icon = "🟢" if r.is_active else "🔴"
        buttons.append([
            InlineKeyboardButton(
                text=f"❌ {status_icon} {r.title} ('{r.pattern}')",
                callback_data=f"ar_del_{r.id}"
            )
        ])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu_auto_response")])

    await call.message.edit_text(
        "📋 **Список правил авто-ответчика:**\nНажмите на правило, чтобы удалить его.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="Markdown"
    )

@router.callback_query(F.data.startswith("ar_del_"))
async def cb_delete_rule(call: CallbackQuery):
    rule_id = int(call.data.replace("ar_del_", ""))
    async with AsyncSessionLocal() as session:
        await session.execute(delete(AutoResponse).where(AutoResponse.id == rule_id))
        await session.commit()

    await call.answer("✅ Правило удалено!", show_alert=True)
    await cb_list_rules(call)

# --- Add Rule Workflow ---
@router.callback_query(F.data == "ar_add_rule")
async def cb_add_rule_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(AddRuleState.title)
    await call.message.edit_text(
        "➕ **Шаг 1 из 3: Название правила**\n\nВведите понятное название правила (например: `Приветствие` или `Цена`):",
        reply_markup=get_back_kb(),
        parse_mode="Markdown"
    )

@router.message(AddRuleState.title)
async def process_title(message: Message, state: FSMContext):
    title = message.text.strip()
    await state.update_data(title=title)
    await state.set_state(AddRuleState.pattern)
    await message.answer(
        "🔍 **Шаг 2 из 3: Ключевое слово / Фраза**\n\n"
        "Введите слово или фразу, при обнаружении которой сработает авто-ответчик (например: `привет` или `где товар`):",
        parse_mode="Markdown"
    )

@router.message(AddRuleState.pattern)
async def process_pattern(message: Message, state: FSMContext):
    pattern = message.text.strip()
    await state.update_data(pattern=pattern)
    await state.set_state(AddRuleState.response_text)
    await message.answer(
        "💬 **Шаг 3 из 3: Текст ответа**\n\n"
        "Введите текст ответа (можно использовать макросы `{buyer_name}`, `{order_id}`, `{lot_name}` и т.д.):",
        parse_mode="Markdown"
    )

@router.message(AddRuleState.response_text)
async def process_response_text(message: Message, state: FSMContext):
    response_text = message.text.strip()
    data = await state.get_data()

    async with AsyncSessionLocal() as session:
        session.add(AutoResponse(
            title=data["title"],
            trigger_type="contains",
            pattern=data["pattern"],
            response_text=response_text,
            is_active=True
        ))
        await session.commit()

    await state.clear()
    await message.answer(
        f"✅ **Правило '{data['title']}' успешно создано!**\n\n"
        f"🔍 **Ключевик:** `{data['pattern']}`\n"
        f"💬 **Ответ:** `{response_text}`",
        reply_markup=get_back_kb(),
        parse_mode="Markdown"
    )
