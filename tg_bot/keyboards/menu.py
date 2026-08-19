from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_main_menu_kb() -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👤 Профиль Starvell", callback_data="feature_profile"),
            InlineKeyboardButton(text="📊 Статистика", callback_data="menu_stats")
        ],
        [
            InlineKeyboardButton(text="🔔 Уведомления", callback_data="menu_notifications"),
            InlineKeyboardButton(text="🎉 Фишки & Чат", callback_data="menu_features")
        ],
        [
            InlineKeyboardButton(text="📦 Запас товаров", callback_data="menu_stock"),
            InlineKeyboardButton(text="⚡ Быстрые ответы", callback_data="menu_quick_replies")
        ],
        [
            InlineKeyboardButton(text="🤖 Авто-ответчик", callback_data="menu_auto_response"),
            InlineKeyboardButton(text="⚡ Авто-выдача", callback_data="menu_auto_delivery")
        ],
        [
            InlineKeyboardButton(text="🚀 Авто-поднятие", callback_data="menu_auto_raise"),
            InlineKeyboardButton(text="🧩 Плагины", callback_data="menu_plugins")
        ],
        [
            InlineKeyboardButton(text="⚙️ Настройки", callback_data="menu_settings"),
            InlineKeyboardButton(text="📢 Канал бота", url="https://t.me/starvell_assistant")
        ]
    ])
    return keyboard

def get_settings_kb(responder: bool, delivery: bool, raise_lots: bool, watermark: bool = True, dumper: bool = False) -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=f"Авто-ответчик: {'🟢 ВКЛ' if responder else '🔴 ВЫКЛ'}",
                callback_data="toggle_auto_responder"
            )
        ],
        [
            InlineKeyboardButton(
                text=f"Авто-выдача: {'🟢 ВКЛ' if delivery else '🔴 ВЫКЛ'}",
                callback_data="toggle_auto_delivery"
            )
        ],
        [
            InlineKeyboardButton(
                text=f"Авто-поднятие: {'🟢 ВКЛ' if raise_lots else '🔴 ВЫКЛ'}",
                callback_data="toggle_auto_raise"
            )
        ],
        [
            InlineKeyboardButton(
                text=f"Водяной знак: {'🟢 ВКЛ' if watermark else '🔴 ВЫКЛ'}",
                callback_data="toggle_watermark_enabled"
            ),
            InlineKeyboardButton(
                text="✏️ Текст водяного знака",
                callback_data="edit_watermark_text"
            )
        ],
        [
            InlineKeyboardButton(text="◀️ Назад", callback_data="menu_main")
        ]
    ])
    return keyboard

def get_notifications_kb(settings: dict) -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=f"💬 Сообщения в чате: {'🟢 ВКЛ' if settings.get('notify_chat_messages', True) else '🔴 ВЫКЛ'}",
                callback_data="toggle_notify_chat_messages"
            )
        ],
        [
            InlineKeyboardButton(
                text=f"📦 Новые заказы: {'🟢 ВКЛ' if settings.get('notify_new_orders', True) else '🔴 ВЫКЛ'}",
                callback_data="toggle_notify_new_orders"
            )
        ],
        [
            InlineKeyboardButton(
                text=f"✅ Оплата / Выдача: {'🟢 ВКЛ' if settings.get('notify_order_delivery', True) else '🔴 ВЫКЛ'}",
                callback_data="toggle_notify_order_delivery"
            )
        ],
        [
            InlineKeyboardButton(
                text=f"⭐ Новые отзывы: {'🟢 ВКЛ' if settings.get('notify_reviews', True) else '🔴 ВЫКЛ'}",
                callback_data="toggle_notify_reviews"
            )
        ],
        [
            InlineKeyboardButton(
                text=f"🚀 Авто-поднятие лотов: {'🟢 ВКЛ' if settings.get('notify_auto_raise', True) else '🔴 ВЫКЛ'}",
                callback_data="toggle_notify_auto_raise"
            )
        ],
        [
            InlineKeyboardButton(
                text=f"📉 Демпинг цен: {'🟢 ВКЛ' if settings.get('notify_dumper', True) else '🔴 ВЫКЛ'}",
                callback_data="toggle_notify_dumper"
            )
        ],
        [
            InlineKeyboardButton(text="◀️ Главное меню", callback_data="menu_main")
        ]
    ])
    return keyboard

def get_stock_menu_kb() -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➕ Добавить товары/ключи", callback_data="stock_add"),
            InlineKeyboardButton(text="📋 Список лотов", callback_data="stock_list")
        ],
        [
            InlineKeyboardButton(text="◀️ Назад", callback_data="menu_main")
        ]
    ])
    return keyboard

def get_back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="menu_main")]
    ])
