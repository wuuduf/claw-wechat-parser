from __future__ import annotations

import json
import logging
from pathlib import Path

from bilibili_api import Credential

from claw_wechat_parser.config import Settings

log = logging.getLogger(__name__)


class BilibiliLogin:
    """Bilibili credential loader.

    当前支持两种来源：
    1. 环境变量 `CLAW_PARSER_BILIBILI_COOKIE`
    2. 状态目录 `cookies/bilibili_credential.json`
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.credential_file: Path = settings.state_dir / "cookies" / "bilibili_credential.json"
        self.credential_file.parent.mkdir(parents=True, exist_ok=True)
        self._credential: Credential | None = None
        self._loaded = False

    @staticmethod
    def _cookies_to_dict(cookies_str: str) -> dict[str, str]:
        res: dict[str, str] = {}
        for cookie in cookies_str.split(";"):
            if "=" not in cookie:
                continue
            name, value = cookie.strip().split("=", 1)
            if name:
                res[name] = value
        return res

    def _save_credential(self) -> None:
        if self._credential is None:
            return
        self.credential_file.write_text(
            json.dumps(self._credential.get_cookies(), ensure_ascii=False),
            encoding="utf-8",
        )
        try:
            self.credential_file.chmod(0o600)
        except OSError:
            pass

    def _load_from_file(self) -> None:
        if not self.credential_file.exists():
            return
        try:
            self._credential = Credential.from_cookies(
                json.loads(self.credential_file.read_text(encoding="utf-8"))
            )
        except Exception as exc:
            log.warning("加载 Bilibili credential 失败：%s", exc)

    async def _init_credential(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if self.settings.bilibili_cookie:
            credential = Credential.from_cookies(self._cookies_to_dict(self.settings.bilibili_cookie))
            try:
                if await credential.check_valid():
                    self._credential = credential
                    self._save_credential()
                    return
                log.warning("CLAW_PARSER_BILIBILI_COOKIE 无效，尝试读取本地凭据")
            except Exception as exc:
                log.warning("校验 Bilibili cookie 失败：%s", exc)
        self._load_from_file()

    @property
    async def credential(self) -> Credential | None:
        await self._init_credential()
        if self._credential is None:
            return None
        try:
            if not await self._credential.check_valid():
                log.warning("Bilibili 凭据已失效")
                return None
            if await self._credential.check_refresh():
                if self._credential.has_ac_time_value() and self._credential.has_bili_jct():
                    await self._credential.refresh()
                    self._save_credential()
        except Exception as exc:
            log.warning("检查/刷新 Bilibili 凭据失败：%s", exc)
        return self._credential
