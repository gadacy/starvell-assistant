import os
import ast
import json
import importlib.util
from typing import Dict, Any, List, Optional
from sqlalchemy import select
from core.database.base import AsyncSessionLocal
from core.database.models import PluginState
from core.logger import logger
from starvell.client import StarvellClient
from starvell.models import StarvellEvent
from services.plugin_api import BasePlugin, PluginContext

class PluginManager:
    """
    Service for managing plugin discovery, dynamic loading/unloading,
    enabling/disabling, settings persistence, and file installation.
    """
    def __init__(self, client: StarvellClient, plugins_dir: Optional[str] = None):
        self.client = client
        self.plugins_dir = plugins_dir or os.path.abspath("plugins")
        os.makedirs(self.plugins_dir, exist_ok=True)
        
        self.loaded_plugins: Dict[str, BasePlugin] = {}
        self.plugin_files: Dict[str, str] = {}  # plugin_name -> filepath
        self.plugin_states: Dict[str, bool] = {} # plugin_name -> is_enabled

    async def get_plugin_state_from_db(self, plugin_name: str) -> tuple[bool, dict]:
        """Fetch enabled state and settings dict from database for a plugin."""
        async with AsyncSessionLocal() as session:
            res = await session.execute(select(PluginState).where(PluginState.name == plugin_name))
            state = res.scalar_one_or_none()
            if not state:
                # Create default entry in DB
                state = PluginState(name=plugin_name, enabled=True, settings_json="{}")
                session.add(state)
                await session.commit()
                return True, {}
            
            try:
                settings_dict = json.loads(state.settings_json or "{}")
            except Exception:
                settings_dict = {}
            return state.enabled, settings_dict

    async def get_plugin_setting(self, plugin_name: str, key: str, default: Any = None) -> Any:
        """Retrieve setting value for a plugin."""
        _, settings_dict = await self.get_plugin_state_from_db(plugin_name)
        if key in settings_dict:
            return settings_dict[key]
        
        # Fallback to schema default if available
        plugin = self.loaded_plugins.get(plugin_name)
        if plugin:
            for item in getattr(plugin, "settings_schema", []):
                if item.get("key") == key and "default" in item:
                    return item["default"]
        return default

    async def set_plugin_setting(self, plugin_name: str, key: str, value: Any):
        """Save a setting value for a plugin in DB."""
        async with AsyncSessionLocal() as session:
            res = await session.execute(select(PluginState).where(PluginState.name == plugin_name))
            state = res.scalar_one_or_none()
            if not state:
                state = PluginState(name=plugin_name, enabled=True, settings_json="{}")
                session.add(state)

            try:
                settings_dict = json.loads(state.settings_json or "{}")
            except Exception:
                settings_dict = {}

            settings_dict[key] = value
            state.settings_json = json.dumps(settings_dict, ensure_ascii=False)
            await session.commit()

    async def load_all_plugins(self):
        """Scan plugins directory, dynamically import .py modules, and initialize plugins."""
        self.loaded_plugins.clear()
        self.plugin_files.clear()
        self.plugin_states.clear()

        if not os.path.exists(self.plugins_dir):
            return

        for fname in os.listdir(self.plugins_dir):
            if fname.endswith(".py") and not fname.startswith("__"):
                fpath = os.path.join(self.plugins_dir, fname)
                await self._load_plugin_from_file(fpath)

        logger.info(f"[PluginManager] Loaded {len(self.loaded_plugins)} plugin(s) from {self.plugins_dir}")

    async def _load_plugin_from_file(self, fpath: str) -> Optional[BasePlugin]:
        mod_name = f"plugins.{os.path.basename(fpath)[:-3]}"
        try:
            spec = importlib.util.spec_from_file_location(mod_name, fpath)
            if not spec or not spec.loader:
                return None
            
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            # Find BasePlugin subclass
            plugin_cls = None
            for attr_name in dir(mod):
                attr = getattr(mod, attr_name)
                if (isinstance(attr, type) and 
                    issubclass(attr, BasePlugin) and 
                    attr is not BasePlugin):
                    plugin_cls = attr
                    break

            if not plugin_cls:
                logger.warning(f"[PluginManager] File {fpath} does not contain a BasePlugin subclass.")
                return None

            instance = plugin_cls()
            name = getattr(instance, "PLUGIN_NAME", os.path.basename(fpath)[:-3])
            
            is_enabled, _ = await self.get_plugin_state_from_db(name)
            
            self.loaded_plugins[name] = instance
            self.plugin_files[name] = fpath
            self.plugin_states[name] = is_enabled

            if is_enabled:
                ctx = PluginContext(plugin_name=name, client=self.client, manager=self)
                await instance.on_load(ctx)
                logger.info(f"[PluginManager] Plugin '{name}' loaded & enabled.")
            else:
                logger.info(f"[PluginManager] Plugin '{name}' loaded (disabled).")

            return instance

        except Exception as e:
            logger.error(f"[PluginManager] Error loading plugin from {fpath}: {e}")
            return None

    async def enable_plugin(self, plugin_name: str) -> bool:
        """Enable a plugin and invoke its on_load callback."""
        if plugin_name not in self.loaded_plugins:
            return False

        plugin = self.loaded_plugins[plugin_name]
        async with AsyncSessionLocal() as session:
            res = await session.execute(select(PluginState).where(PluginState.name == plugin_name))
            state = res.scalar_one_or_none()
            if state:
                state.enabled = True
            else:
                session.add(PluginState(name=plugin_name, enabled=True))
            await session.commit()

        self.plugin_states[plugin_name] = True
        ctx = PluginContext(plugin_name=plugin_name, client=self.client, manager=self)
        try:
            await plugin.on_load(ctx)
            logger.info(f"[PluginManager] Plugin '{plugin_name}' enabled.")
            return True
        except Exception as e:
            logger.error(f"[PluginManager] Error enabling plugin '{plugin_name}': {e}")
            return False

    async def disable_plugin(self, plugin_name: str) -> bool:
        """Disable a plugin and invoke its on_unload callback."""
        if plugin_name not in self.loaded_plugins:
            return False

        plugin = self.loaded_plugins[plugin_name]
        async with AsyncSessionLocal() as session:
            res = await session.execute(select(PluginState).where(PluginState.name == plugin_name))
            state = res.scalar_one_or_none()
            if state:
                state.enabled = False
            else:
                session.add(PluginState(name=plugin_name, enabled=False))
            await session.commit()

        self.plugin_states[plugin_name] = False
        try:
            await plugin.on_unload()
            logger.info(f"[PluginManager] Plugin '{plugin_name}' disabled.")
            return True
        except Exception as e:
            logger.error(f"[PluginManager] Error disabling plugin '{plugin_name}': {e}")
            return False

    async def install_plugin_file(self, file_bytes: bytes, filename: str) -> tuple[bool, str]:
        """
        Save and load a new plugin script from Telegram upload.
        Strictly requires .py extension.
        """
        if not filename.lower().endswith(".py"):
            return False, "❌ Ошибка: разрешена загрузка только файлов с расширением `.py`!"

        # Validate python syntax
        try:
            ast.parse(file_bytes.decode("utf-8"))
        except Exception as e:
            return False, f"❌ Ошибка синтаксиса Python в файле `{filename}`:\n`{e}`"

        safe_name = "".join(c for c in filename if c.isalnum() or c in ("_", "-", "."))
        if not safe_name.endswith(".py"):
            safe_name += ".py"

        target_path = os.path.join(self.plugins_dir, safe_name)
        with open(target_path, "wb") as f:
            f.write(file_bytes)

        instance = await self._load_plugin_from_file(target_path)
        if not instance:
            if os.path.exists(target_path):
                os.remove(target_path)
            return False, f"❌ Файл `{filename}` не содержит класс-наследник `BasePlugin`."

        name = getattr(instance, "PLUGIN_NAME", safe_name[:-3])
        return True, name

    async def delete_plugin(self, plugin_name: str) -> tuple[bool, str]:
        """Delete a plugin file from disk and state from DB."""
        if plugin_name in self.loaded_plugins:
            try:
                await self.loaded_plugins[plugin_name].on_unload()
            except Exception:
                pass

        fpath = self.plugin_files.get(plugin_name)
        if fpath and os.path.exists(fpath):
            try:
                os.remove(fpath)
            except Exception as e:
                logger.error(f"[PluginManager] Error deleting file {fpath}: {e}")

        async with AsyncSessionLocal() as session:
            res = await session.execute(select(PluginState).where(PluginState.name == plugin_name))
            state = res.scalar_one_or_none()
            if state:
                await session.delete(state)
                await session.commit()

        self.loaded_plugins.pop(plugin_name, None)
        self.plugin_files.pop(plugin_name, None)
        self.plugin_states.pop(plugin_name, None)

        logger.info(f"[PluginManager] Plugin '{plugin_name}' deleted.")
        return True, f"✅ Плагин `{plugin_name}` успешно удален."

    async def dispatch_event(self, event: StarvellEvent):
        """Pass incoming events to all enabled plugins."""
        for name, plugin in self.loaded_plugins.items():
            if self.plugin_states.get(name, False):
                try:
                    await plugin.on_event(event)
                except Exception as e:
                    logger.error(f"[PluginManager] Error dispatching event to plugin '{name}': {e}")

    async def get_all_plugins_info(self) -> List[Dict[str, Any]]:
        """Return list of dicts with plugin metadata and settings for UI rendering."""
        result = []
        for name, plugin in self.loaded_plugins.items():
            is_enabled = self.plugin_states.get(name, False)
            _, settings_dict = await self.get_plugin_state_from_db(name)
            
            result.append({
                "name": name,
                "version": getattr(plugin, "PLUGIN_VERSION", "1.0.0"),
                "description": getattr(plugin, "PLUGIN_DESCRIPTION", "Без описания"),
                "author": getattr(plugin, "PLUGIN_AUTHOR", "Автор не указан"),
                "enabled": is_enabled,
                "settings_schema": getattr(plugin, "settings_schema", []),
                "settings": settings_dict,
                "file": os.path.basename(self.plugin_files.get(name, ""))
            })
        return result
