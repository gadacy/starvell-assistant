from typing import List, Dict, Any
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_plugins_list_kb(plugins_info: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    keyboard = []
    
    # Plugin list buttons
    for p in plugins_info:
        status_icon = "🟢" if p.get("enabled") else "🔴"
        name = p.get("name", "Unknown")
        btn_text = f"{status_icon} {name} (v{p.get('version', '1.0')})"
        keyboard.append([InlineKeyboardButton(text=btn_text, callback_data=f"plugin_view:{name}")])

    # Action buttons
    keyboard.append([InlineKeyboardButton(text="➕ Добавить плагин", callback_data="plugin_add")])
    keyboard.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu_main")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_plugin_detail_kb(plugin_info: Dict[str, Any]) -> InlineKeyboardMarkup:
    name = plugin_info.get("name", "")
    enabled = plugin_info.get("enabled", False)
    schema = plugin_info.get("settings_schema", [])
    settings = plugin_info.get("settings", {})

    keyboard = [
        [
            InlineKeyboardButton(
                text=f"Статус плагина: {'🟢 ВКЛЮЧЕН' if enabled else '🔴 ВЫКЛЮЧЕН'}",
                callback_data=f"plugin_toggle:{name}"
            )
        ]
    ]

    if name == "PriceDumper":
        keyboard.append([
            InlineKeyboardButton(text="📋 Правила демпинга", callback_data="menu_dumper")
        ])

    # Dynamic settings rows
    for item in schema:
        key = item.get("key")
        label = item.get("label", key)
        stype = item.get("type", "text")
        val = settings.get(key, item.get("default"))

        if stype == "bool":
            is_on = str(val).lower() == "true" if isinstance(val, str) else bool(val)
            btn_text = f"{label}: {'🟢 ВКЛ' if is_on else '🔴 ВЫКЛ'}"
            keyboard.append([
                InlineKeyboardButton(text=btn_text, callback_data=f"plugin_set_toggle:{name}:{key}")
            ])
        else: # text or string
            keyboard.append([
                InlineKeyboardButton(text=f"✏️ {label}", callback_data=f"plugin_set_edit:{name}:{key}")
            ])

    keyboard.append([
        InlineKeyboardButton(text="🗑️ Удалить плагин", callback_data=f"plugin_delete:{name}")
    ])
    keyboard.append([
        InlineKeyboardButton(text="◀️ К плагинам", callback_data="menu_plugins")
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)
