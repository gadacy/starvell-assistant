from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select, delete
from core.database.base import AsyncSessionLocal
from core.database.models import DumperRule, BotSetting
from core.logger import logger
from tg_bot.keyboards.menu import get_back_kb

router = Router()

class DumperAddState(StatesGroup):
    waiting_for_lot_id = State()
    waiting_for_min_price = State()
    waiting_for_step = State()

def get_dumper_menu_kb(rules_count: int, is_enabled: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=f"Статус плагина PriceDumper: {'🟢 ВКЛ' if is_enabled else '🔴 ВЫКЛ'}",
                callback_data="plugin_toggle:PriceDumper"
            )
        ],
        [
            InlineKeyboardButton(text="➕ Добавить правило для лота", callback_data="dumper_add_rule")
        ],
        [
            InlineKeyboardButton(text=f"📋 Все правила ({rules_count})", callback_data="dumper_list_rules")
        ],
        [
            InlineKeyboardButton(text="◀️ Назад к плагину", callback_data="plugin_view:PriceDumper")
        ]
    ])

@router.callback_query(F.data == "menu_dumper")
async def cb_dumper_menu(call: CallbackQuery):
    async with AsyncSessionLocal() as session:
        from core.database.models import PluginState
        res_e = await session.execute(select(PluginState).where(PluginState.name == "PriceDumper"))
        p_state = res_e.scalar_one_or_none()
        is_enabled = p_state.enabled if p_state else True

        res_r = await session.execute(select(DumperRule))
        rules = res_r.scalars().all()

    text = (
        "📉 **Панель Авто-демпинга цен (Плагин PriceDumper):**\n\n"
        "Автодемпер отслеживает конкурентов и сбрасывает цену вашего лота на заданный шаг, "
        "но **НЕ НИЖЕ указанного порога (минимальной цены)!**\n\n"
        f"📊 **Активных правил:** `{len(rules)}`"
    )
    await call.message.edit_text(text, reply_markup=get_dumper_menu_kb(len(rules), is_enabled), parse_mode="Markdown")

@router.callback_query(F.data == "dumper_list_rules")
async def cb_dumper_list(call: CallbackQuery):
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(DumperRule))
        rules = res.scalars().all()

    if not rules:
        await call.message.edit_text(
            "📋 **Правила автодемпинга отсутствуют.**\nНажмите 'Добавить правило для лота', чтобы настроить порог цен.",
            reply_markup=get_back_kb(),
            parse_mode="Markdown"
        )
        return

    buttons = []
    for r in rules:
        title = r.lot_title or f"Лот {r.lot_id}"
        buttons.append([
            InlineKeyboardButton(
                text=f"❌ {title[:20]} (Мин: {r.min_price}₽, Шаг: {r.step}₽)",
                callback_data=f"dumper_del_{r.id}"
            )
        ])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu_dumper")])

    await call.message.edit_text(
        "📋 **Список правил автодемпинга:**\nНажмите на правило, чтобы удалить его.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="Markdown"
    )

@router.callback_query(F.data.startswith("dumper_del_"))
async def cb_dumper_delete(call: CallbackQuery):
    rule_id = int(call.data.replace("dumper_del_", ""))
    async with AsyncSessionLocal() as session:
        await session.execute(delete(DumperRule).where(DumperRule.id == rule_id))
        await session.commit()

    await call.answer("✅ Правило удалено!", show_alert=True)
    await cb_dumper_list(call)

# --- Add New Per-Lot Dumper Rule Workflow ---
@router.callback_query(F.data == "dumper_add_rule")
async def cb_dumper_add_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(DumperAddState.waiting_for_lot_id)
    await call.message.edit_text(
        "➕ **Шаг 1 из 3: Укажите ID лота или название**\n\n"
        "Введите ID лота на Starvell (например, `101` или название лота, например `Steam Key`):",
        reply_markup=get_back_kb(),
        parse_mode="Markdown"
    )

@router.message(DumperAddState.waiting_for_lot_id)
async def process_dumper_lot_id(message: Message, state: FSMContext):
    lot_id = message.text.strip()
    if not lot_id:
        await message.answer("⚠️ Введите корректный ID лота.")
        return

    await state.update_data(lot_id=lot_id)
    await state.set_state(DumperAddState.waiting_for_min_price)
    await message.answer(
        "🛑 **Шаг 2 из 3: Укажите минимальный порог цены (RUB)**\n\n"
        "Ниже этой суммы бот **НИКОГДА** не опустит цену вашего лота!\n\n"
        "Пример:\n`50` (для первого лота) или `80` (для второго лота):",
        parse_mode="Markdown"
    )

@router.message(DumperAddState.waiting_for_min_price)
async def process_dumper_min_price(message: Message, state: FSMContext):
    try:
        min_price = float(message.text.strip().replace(",", "."))
        if min_price <= 0:
            raise ValueError
    except ValueError:
        await message.answer("⚠️ Введите корректное число для минимальной цены (например: 50).")
        return

    await state.update_data(min_price=min_price)
    await state.set_state(DumperAddState.waiting_for_step)
    await message.answer(
        "📉 **Шаг 3 из 3: Укажите шаг сброса цены (RUB)**\n\n"
        "На сколько рублей перебивать цену конкурента? (например: `1` или `0.5`):",
        parse_mode="Markdown"
    )

@router.message(DumperAddState.waiting_for_step)
async def process_dumper_step(message: Message, state: FSMContext):
    try:
        step = float(message.text.strip().replace(",", "."))
        if step <= 0:
            raise ValueError
    except ValueError:
        await message.answer("⚠️ Введите корректный шаг сброса цены (например: 1).")
        return

    data = await state.get_data()
    lot_id = data["lot_id"]
    min_price = data["min_price"]

    async with AsyncSessionLocal() as session:
        # Check if rule already exists for this lot
        res = await session.execute(select(DumperRule).where(DumperRule.lot_id == lot_id))
        rule = res.scalar_one_or_none()
        if rule:
            rule.min_price = min_price
            rule.step = step
            rule.is_active = True
        else:
            session.add(DumperRule(
                lot_id=lot_id,
                lot_title=f"Лот #{lot_id}",
                min_price=min_price,
                step=step,
                is_active=True
            ))
        await session.commit()

    await state.clear()
    await message.answer(
        f"✅ **Правило демпинга успешно сохранено!**\n\n"
        f"📦 **Лот ID:** `{lot_id}`\n"
        f"🛑 **Порог цены:** **{min_price} ₽** (бот не опустит цену ниже!)\n"
        f"📉 **Шаг перебивания:** **{step} ₽**",
        reply_markup=get_back_kb(),
        parse_mode="Markdown"
    )
