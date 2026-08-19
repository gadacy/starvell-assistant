from typing import Optional
from aiogram import Router, F
from aiogram.types import CallbackQuery
from services.stats_service import StatsService
from tg_bot.keyboards.menu import get_back_kb
from starvell.client import StarvellClient

router = Router()
_starvell_client: Optional[StarvellClient] = None

def set_client(client: StarvellClient):
    global _starvell_client
    _starvell_client = client

@router.callback_query(F.data == "menu_stats")
async def cb_stats(call: CallbackQuery):
    await call.answer("📊 Загрузка актуальной статистики...")
    stats = await StatsService.get_summary_stats(_starvell_client)

    today = stats.get("today", {})
    yesterday = stats.get("yesterday", {})
    days_3 = stats.get("days_3", {})
    days_7 = stats.get("days_7", {})
    month_1 = stats.get("month_1", {})
    month_3 = stats.get("month_3", {})
    year_1 = stats.get("year_1", {})
    all_time = stats.get("all_time", {})
    stock_available = stats.get("stock_available", 0)

    text = (
        "📊 **Детальная статистика продаж и доходов:**\n\n"
        f"☀️ **Сегодня (24ч):** {today.get('count', 0)} зак. | **{today.get('revenue', 0.0):.2f} RUB**\n"
        f"🌙 **Вчера (24-48ч):** {yesterday.get('count', 0)} зак. | **{yesterday.get('revenue', 0.0):.2f} RUB**\n"
        f"📅 **За 3 суток (72ч):** {days_3.get('count', 0)} зак. | **{days_3.get('revenue', 0.0):.2f} RUB**\n"
        f"🗓️ **За 7 суток:** {days_7.get('count', 0)} зак. | **{days_7.get('revenue', 0.0):.2f} RUB**\n"
        f"📈 **За месяц (30д):** {month_1.get('count', 0)} зак. | **{month_1.get('revenue', 0.0):.2f} RUB**\n"
        f"📊 **За 3 месяца (90д):** {month_3.get('count', 0)} зак. | **{month_3.get('revenue', 0.0):.2f} RUB**\n"
        f"📅 **За год (365д):** {year_1.get('count', 0)} зак. | **{year_1.get('revenue', 0.0):.2f} RUB**\n"
        f"🏆 **За всё время:** {all_time.get('count', 0)} зак. | **{all_time.get('revenue', 0.0):.2f} RUB**\n\n"
        f"📦 **Товаров в наличии:** {stock_available} шт."
    )

    await call.message.edit_text(text, reply_markup=get_back_kb(), parse_mode="Markdown")
