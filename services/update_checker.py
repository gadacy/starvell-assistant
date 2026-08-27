import sys
import os
import asyncio
import httpx
from typing import Tuple, Optional, Dict, Any
from core.logger import logger
from version import __version__, VERSION_URL

class UpdateCheckerService:
    @staticmethod
    async def check_for_updates() -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Checks raw GitHub version.json for updates.
        Returns: (has_update: bool, message: str, update_info: dict)
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(VERSION_URL)
                if res.status_code == 200:
                    data = res.json()
                    remote_ver = str(data.get("version", "")).strip()
                    if remote_ver and UpdateCheckerService.is_newer(remote_ver, __version__):
                        changelog = data.get("changelog", "Улучшения и исправления ошибок.")
                        msg = (
                            f"🔔 **Доступно новое обновление: v{remote_ver}!** (Текущая: v{__version__})\n\n"
                            f"📝 **Изменения:**\n{changelog}"
                        )
                        return True, msg, data
                    else:
                        return False, f"✅ У вас установлена последняя версия бота (**v{__version__}**).", data
        except Exception as e:
            logger.warning(f"[UpdateChecker] Ошибка проверки обновлений: {e}")
            return False, f"⚠️ Не удалось проверить обновления на GitHub. (Текущая версия: v{__version__})", None

        return False, f"✅ У вас установлена последняя версия бота (**v{__version__}**).", None

    @staticmethod
    def is_newer(remote: str, current: str) -> bool:
        def parse(v: str):
            return [int(x) for x in v.replace("v", "").split(".") if x.isdigit()]
        try:
            return parse(remote) > parse(current)
        except Exception:
            return remote != current

    @staticmethod
    async def perform_git_pull() -> Tuple[bool, str]:
        """
        Executes git pull origin main asynchronously.
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                "git", "pull", "origin", "main",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0:
                output = stdout.decode("utf-8", errors="ignore").strip()
                logger.info(f"[UpdateChecker] git pull success: {output}")
                return True, output
            else:
                err = stderr.decode("utf-8", errors="ignore").strip()
                logger.error(f"[UpdateChecker] git pull error (code {proc.returncode}): {err}")
                return False, err
        except Exception as e:
            logger.error(f"[UpdateChecker] Exception during git pull: {e}")
            return False, str(e)

    @staticmethod
    def restart_bot():
        """
        Restarts current Python process cleanly.
        """
        logger.info("[UpdateChecker] Выполняется перезапуск процесса бота...")
        python = sys.executable
        os.execl(python, python, *sys.argv)
