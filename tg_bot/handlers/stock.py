from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select, func
from core.database.base import AsyncSessionLocal
from core.database.models import StockItem
from tg_bot.keyboards.menu import get_stock_menu_kb, get_back_kb

router = Router()

class AddStockState(StatesGroup):
    waiting_for_lot_id = State()
    waiting_for_items = State()

@router.callback_query(F.data == "menu_stock")
async def cb_stock_menu(call: CallbackQuery):
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(
                StockItem.lot_id,
                StockItem.lot_name,
                func.count(StockItem.id)
            ).where(StockItem.is_used == False).group_by(StockItem.lot_id)
        )
        stocks = res.all()

    text = "📦 **Запасы цифровых товаров для авто-выдачи:**\n\n"
    if not stocks:
        text += "❌ В базе нет доступных товаров.\nДобавьте товары кнопкой ниже!"
    else:
        for lot_id, lot_name, count in stocks:
            name_str = lot_name or f"Лот #{lot_id}"
            text += f"🔹 `{lot_id}`: **{name_str}** — **{count} шт.**\n"

    await call.message.edit_text(text, reply_markup=get_stock_menu_kb(), parse_mode="Markdown")

@router.callback_query(F.data == "stock_add")
async def cb_stock_add(call: CallbackQuery, state: FSMContext):
    await state.set_state(AddStockState.waiting_for_lot_id)
    await call.message.edit_text(
        "✏️ **Введите ID лота Starvell**, для которого вы хотите добавить товары/ключи:\n\n"
        "(ID лота можно скопировать из URL лота или списка в Starvell)",
        reply_markup=get_back_kb(),
        parse_mode="Markdown"
    )

@router.message(AddStockState.waiting_for_lot_id)
async def process_lot_id(message: Message, state: FSMContext):
    lot_id = message.text.strip()
    await state.update_data(lot_id=lot_id)
    await state.set_state(AddStockState.waiting_for_items)
    await message.answer(
        f"📝 **Лот ID:** `{lot_id}`\n\n"
        f"Отправьте товары (ключи, аккаунты, промокоды) **по одному в каждой строке**:\n\n"
        f"Пример:\n"
        f"`KEY-1111-2222`\n"
        f"`KEY-3333-4444`\n"
        f"`login:password`",
        parse_mode="Markdown"
    )

@router.message(AddStockState.waiting_for_items)
async def process_stock_items(message: Message, state: FSMContext):
    data = await state.get_data()
    lot_id = data.get("lot_id")
    lines = [line.strip() for line in message.text.split("\n") if line.strip()]

    if not lines:
        await message.answer("⚠️ Вы отправили пустой текст. Попробуйте еще раз.")
        return

    added_count = 0
    async with AsyncSessionLocal() as session:
        for line in lines:
            item = StockItem(
                lot_id=str(lot_id),
                item_data=line,
                is_used=False
            )
            session.add(item)
            added_count += 1
        await session.commit()

    await state.clear()
    await message.answer(
        f"✅ **Успешно добавлено {added_count} шт. товаров** для лота `{lot_id}`!",
        reply_markup=get_stock_menu_kb(),
        parse_mode="Markdown"
    )
