import html

from aiogram import Router, F
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select, func
from core.database.base import AsyncSessionLocal
from core.database.models import StockItem
from tg_bot.keyboards.menu import get_stock_menu_kb, get_back_kb

router = Router()
LOTS_PER_PAGE = 10
PREVIEW_ITEMS = 10

class AddStockState(StatesGroup):
    waiting_for_lot_id = State()
    waiting_for_items = State()

@router.callback_query(F.data == "menu_stock")
async def cb_stock_menu(call: CallbackQuery):
    async with AsyncSessionLocal() as session:
        total = (await session.execute(
            select(func.count(StockItem.id)).where(StockItem.is_used.is_(False))
        )).scalar_one()
        lots = (await session.execute(
            select(func.count(func.distinct(StockItem.lot_id))).where(StockItem.is_used.is_(False))
        )).scalar_one()

    await call.message.edit_text(
        f"📦 <b>Запас для автовыдачи</b>\n\nДоступно: <b>{total} шт.</b> в <b>{lots} лотах</b>.\n"
        "Откройте список лотов, чтобы проверить содержимое и скачать набор.",
        reply_markup=get_stock_menu_kb(), parse_mode="HTML"
    )


@router.callback_query(F.data == "stock_list")
@router.callback_query(F.data.startswith("stock_list:"))
async def cb_stock_list(call: CallbackQuery):
    try:
        page = max(0, int(call.data.split(":", 1)[1])) if ":" in call.data else 0
    except ValueError:
        page = 0

    async with AsyncSessionLocal() as session:
        grouped = (
            select(
                StockItem.lot_id.label("lot_id"),
                func.min(StockItem.id).label("first_id"),
                func.min(StockItem.lot_name).label("lot_name"),
                func.count(StockItem.id).label("count"),
            )
            .where(StockItem.is_used.is_(False))
            .group_by(StockItem.lot_id)
        )
        total_lots = (await session.execute(
            select(func.count()).select_from(grouped.subquery())
        )).scalar_one()
        pages = max(1, (total_lots + LOTS_PER_PAGE - 1) // LOTS_PER_PAGE)
        page = min(page, pages - 1)
        lots = (await session.execute(
            grouped.order_by(StockItem.lot_id).limit(LOTS_PER_PAGE).offset(page * LOTS_PER_PAGE)
        )).all()

    buttons = [
        [InlineKeyboardButton(
            text=f"📦 {(lot_name or lot_id)[:40]} — {count} шт.",
            callback_data=f"stock_view:{first_id}",
        )]
        for lot_id, first_id, lot_name, count in lots
    ]
    navigation = []
    if page > 0:
        navigation.append(InlineKeyboardButton(text="◀️", callback_data=f"stock_list:{page - 1}"))
    if page + 1 < pages:
        navigation.append(InlineKeyboardButton(text="▶️", callback_data=f"stock_list:{page + 1}"))
    if navigation:
        buttons.append(navigation)
    buttons.append([InlineKeyboardButton(text="◀️ Запас товаров", callback_data="menu_stock")])
    text = f"📋 <b>Лоты с доступными товарами</b> · {page + 1}/{pages}"
    if not lots:
        text += "\n\nПока нет товаров для автовыдачи."
    await call.message.edit_text(
        text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML"
    )


async def get_lot_id(session, first_id: int) -> str | None:
    return (await session.execute(
        select(StockItem.lot_id).where(StockItem.id == first_id)
    )).scalar_one_or_none()


@router.callback_query(F.data.startswith("stock_view:"))
async def cb_stock_view(call: CallbackQuery):
    if call.message.chat.type != "private":
        await call.answer("Просмотр товаров доступен в личном чате с ботом.", show_alert=True)
        return
    try:
        first_id = int(call.data.split(":", 1)[1])
    except ValueError:
        await call.answer("Лот не найден.", show_alert=True)
        return

    async with AsyncSessionLocal() as session:
        lot_id = await get_lot_id(session, first_id)
        if lot_id is None:
            await call.answer("Лот не найден.", show_alert=True)
            return
        count = (await session.execute(
            select(func.count(StockItem.id)).where(
                StockItem.lot_id == lot_id, StockItem.is_used.is_(False)
            )
        )).scalar_one()
        items = (await session.execute(
            select(StockItem.item_data).where(
                StockItem.lot_id == lot_id, StockItem.is_used.is_(False)
            ).order_by(StockItem.id).limit(PREVIEW_ITEMS)
        )).scalars().all()

    # Keep all ten rows visible within Telegram's message size limit.
    shortened = any(len(item) > 250 for item in items)
    preview = "\n".join(
        f"{index}. {item[:250]}{'…' if len(item) > 250 else ''}"
        for index, item in enumerate(items, 1)
    )
    text = (
        f"📦 <b>Лот {html.escape(lot_id)}</b>\n"
        f"Доступно: <b>{count} шт.</b>\n\n"
        f"Первые {len(items)} записей{' (длинные строки сокращены)' if shortened else ''}:\n"
        f"<pre>{html.escape(preview)}</pre>"
        if items else f"📦 <b>Лот {html.escape(lot_id)}</b>\n\nДоступных товаров больше нет."
    )
    buttons = []
    if items:
        buttons.append([InlineKeyboardButton(
            text="📥 Скачать весь доступный набор", callback_data=f"stock_download:{first_id}"
        )])
    buttons.append([InlineKeyboardButton(text="◀️ Список лотов", callback_data="stock_list")])
    await call.message.edit_text(
        text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("stock_download:"))
async def cb_stock_download(call: CallbackQuery):
    if call.message.chat.type != "private":
        await call.answer("Скачивание доступно в личном чате с ботом.", show_alert=True)
        return
    try:
        first_id = int(call.data.split(":", 1)[1])
    except ValueError:
        await call.answer("Лот не найден.", show_alert=True)
        return

    async with AsyncSessionLocal() as session:
        lot_id = await get_lot_id(session, first_id)
        if lot_id is None:
            await call.answer("Лот не найден.", show_alert=True)
            return
        items = (await session.execute(
            select(StockItem.item_data).where(
                StockItem.lot_id == lot_id, StockItem.is_used.is_(False)
            ).order_by(StockItem.id)
        )).scalars().all()

    if not items:
        await call.answer("Доступных товаров больше нет.", show_alert=True)
        return
    document = BufferedInputFile(
        ("\n".join(items) + "\n").encode("utf-8"), filename=f"stock_lot_{first_id}.txt"
    )
    try:
        await call.message.answer_document(
            document, caption=f"Полный доступный набор лота {lot_id}: {len(items)} шт."
        )
    except TelegramAPIError:
        await call.answer("Не удалось отправить файл. Попробуйте ещё раз.", show_alert=True)
        return
    await call.answer("Файл отправлен.")

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
