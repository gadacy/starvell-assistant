import io
from typing import Optional
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from tg_bot.handlers.common import is_admin
from tg_bot.keyboards.plugins import get_plugins_list_kb, get_plugin_detail_kb
from tg_bot.keyboards.menu import get_back_kb
from services.plugin_manager import PluginManager

router = Router()
_plugin_manager: Optional[PluginManager] = None

def set_plugin_manager(manager: PluginManager):
    global _plugin_manager
    _plugin_manager = manager

class PluginFSM(StatesGroup):
    waiting_for_file = State()
    waiting_for_setting_value = State()

@router.message(Command("plugins"))
@router.callback_query(F.data == "menu_plugins")
async def handle_plugins_menu(event: Message | CallbackQuery, state: FSMContext):
    user_id = event.from_user.id
    if not is_admin(user_id):
        return

    await state.clear()
    if not _plugin_manager:
        text = "❌ Ошибка: Менеджер плагинов не инициализирован."
        if isinstance(event, CallbackQuery):
            await event.message.edit_text(text, reply_markup=get_back_kb())
        else:
            await event.answer(text, reply_markup=get_back_kb())
        return

    plugins_info = await _plugin_manager.get_all_plugins_info()
    text = (
        "🧩 **Управление плагинами (Starvell Assistant):**\n\n"
        f"Установлено плагинов: **{len(plugins_info)}**\n"
        "Нажмите на плагин для управления его настройками и статусом или добавьте новый."
    )
    kb = get_plugins_list_kb(plugins_info)

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    else:
        await event.answer(text, reply_markup=kb, parse_mode="Markdown")

@router.callback_query(F.data.startswith("plugin_view:"))
async def cb_plugin_view(call: CallbackQuery):
    if not is_admin(call.from_user.id) or not _plugin_manager:
        return

    name = call.data.split(":", 1)[1]
    plugins = await _plugin_manager.get_all_plugins_info()
    plugin = next((p for p in plugins if p["name"] == name), None)

    if not plugin:
        await call.answer("❌ Плагин не найден.", show_alert=True)
        return

    status_str = "🟢 ВКЛЮЧЕН" if plugin["enabled"] else "🔴 ВЫКЛЮЧЕН"
    text = (
        f"🧩 **Плагин:** `{plugin['name']}`\n"
        f"📌 **Версия:** {plugin['version']}\n"
        f"👤 **Автор:** {plugin['author']}\n"
        f"📁 **Файл:** `{plugin['file']}`\n"
        f"⚡ **Статус:** {status_str}\n\n"
        f"📝 **Описание:**\n{plugin['description']}\n\n"
        f"👇 **Панель управления и настройки плагина:**"
    )
    kb = get_plugin_detail_kb(plugin)
    await call.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")

@router.callback_query(F.data.startswith("plugin_toggle:"))
async def cb_plugin_toggle(call: CallbackQuery):
    if not is_admin(call.from_user.id) or not _plugin_manager:
        return

    name = call.data.split(":", 1)[1]
    is_enabled = _plugin_manager.plugin_states.get(name, False)

    if is_enabled:
        await _plugin_manager.disable_plugin(name)
        await call.answer(f"🔴 Плагин {name} выключен.")
    else:
        await _plugin_manager.enable_plugin(name)
        await call.answer(f"🟢 Плагин {name} включен.")

    await cb_plugin_view(call)

@router.callback_query(F.data.startswith("plugin_set_toggle:"))
async def cb_plugin_set_toggle(call: CallbackQuery):
    if not is_admin(call.from_user.id) or not _plugin_manager:
        return

    _, name, key = call.data.split(":", 2)
    cur_val = await _plugin_manager.get_plugin_setting(name, key, False)
    new_val = not (str(cur_val).lower() == "true" if isinstance(cur_val, str) else bool(cur_val))

    await _plugin_manager.set_plugin_setting(name, key, new_val)
    await call.answer(f"Переключено: {key} -> {new_val}")
    await cb_plugin_view(call)

@router.callback_query(F.data.startswith("plugin_set_edit:"))
async def cb_plugin_set_edit(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return

    _, name, key = call.data.split(":", 2)
    await state.update_data(plugin_name=name, setting_key=key)
    await state.set_state(PluginFSM.waiting_for_setting_value)

    cur_val = await _plugin_manager.get_plugin_setting(name, key, "")
    await call.message.edit_text(
        f"✏️ **Редактирование настройки плагина `{name}`**\n\n"
        f"Параметр: `{key}`\n"
        f"Текущее значение:\n`{cur_val}`\n\n"
        f"Отправьте новое значение сообщением в чат:",
        reply_markup=get_back_kb(),
        parse_mode="Markdown"
    )

@router.message(PluginFSM.waiting_for_setting_value)
async def process_setting_value(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id) or not _plugin_manager:
        return

    data = await state.get_data()
    name = data.get("plugin_name")
    key = data.get("setting_key")
    new_text = message.text.strip() if message.text else ""

    if name and key:
        await _plugin_manager.set_plugin_setting(name, key, new_text)
        await state.clear()
        await message.answer(
            f"✅ Настройка `{key}` для плагина `{name}` обновлена на:\n`{new_text}`",
            reply_markup=get_back_kb(),
            parse_mode="Markdown"
        )

@router.callback_query(F.data.startswith("plugin_delete:"))
async def cb_plugin_delete(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id) or not _plugin_manager:
        return

    name = call.data.split(":", 1)[1]
    ok, msg = await _plugin_manager.delete_plugin(name)
    await call.answer(msg, show_alert=True)
    await handle_plugins_menu(call, state)

@router.callback_query(F.data == "plugin_add")
async def cb_plugin_add(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return

    await state.set_state(PluginFSM.waiting_for_file)
    await call.message.edit_text(
        "📥 **Добавление нового плагина:**\n\n"
        "Отправьте файл плагина в этот чат (принимаются **только `.py`** файлы).\n"
        "Плагин будет автоматически проверен, сохранен и подключен!",
        reply_markup=get_back_kb(),
        parse_mode="Markdown"
    )

@router.message(PluginFSM.waiting_for_file)
async def process_plugin_file(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id) or not _plugin_manager:
        return

    if not message.document:
        await message.answer("⚠️ Пожалуйста, отправьте файл плагина `.py` как документ.")
        return

    fname = message.document.file_name or "plugin.py"
    if not fname.lower().endswith(".py"):
        await message.answer(
            "❌ **Загрузка отклонена!**\n"
            "Разрешено загружать **исключительно файлы с расширением `.py`**.",
            parse_mode="Markdown"
        )
        return

    try:
        buffer = io.BytesIO()
        await message.bot.download(message.document, destination=buffer)
        file_bytes = buffer.getvalue()

        ok, result_msg = await _plugin_manager.install_plugin_file(file_bytes, fname)
        await state.clear()

        if ok:
            await message.answer(
                f"🎉 **Плагин успешно установлен!**\n\n"
                f"Название плагина: `{result_msg}`\n"
                f"Статус: 🟢 Активен\n\n"
                f"Вы можете настроить его в меню плагинов.",
                reply_markup=get_back_kb(),
                parse_mode="Markdown"
            )
        else:
            await message.answer(
                f"❌ **Ошибка установки плагина:**\n\n{result_msg}",
                reply_markup=get_back_kb(),
                parse_mode="Markdown"
            )
    except Exception as e:
        await state.clear()
        await message.answer(f"❌ Ошибка скачивания файла: {e}", reply_markup=get_back_kb())
