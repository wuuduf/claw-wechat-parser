from __future__ import annotations

import base64
import json
import logging
import random
from dataclasses import dataclass, field
from typing import Any

import httpx

from claw_wechat_parser.config import Settings
from claw_wechat_parser.logging import redact

log = logging.getLogger(__name__)


def _client_version(version: str) -> int:
    parts = [int(p) if p.isdigit() else 0 for p in version.split(".")[:3]]
    parts += [0] * (3 - len(parts))
    major, minor, patch = parts[:3]
    return ((major & 0xFF) << 16) | ((minor & 0xFF) << 8) | (patch & 0xFF)


def _random_wechat_uin() -> str:
    return base64.b64encode(str(random.getrandbits(32)).encode()).decode()


@dataclass(slots=True)
class WeixinApi:
    settings: Settings
    base_url: str | None = None
    token: str | None = None
    client: httpx.AsyncClient = field(init=False)

    def __post_init__(self) -> None:
        self.base_url = (self.base_url or self.settings.api_base_url).rstrip("/")
        self.client = httpx.AsyncClient(timeout=self.settings.api_timeout_s)

    async def close(self) -> None:
        await self.client.aclose()

    def _common_headers(self, body: str | None = None, auth: bool = True) -> dict[str, str]:
        headers = {
            "iLink-App-Id": self.settings.ilink_app_id,
            "iLink-App-ClientVersion": str(_client_version(self.settings.channel_version)),
            "X-WECHAT-UIN": _random_wechat_uin(),
        }
        if body is not None:
            headers.update({"Content-Type": "application/json", "Content-Length": str(len(body.encode()))})
        if auth and self.token:
            headers.update({"AuthorizationType": "ilink_bot_token", "Authorization": f"Bearer {self.token}"})
        return headers

    def _with_base_info(self, data: dict[str, Any]) -> dict[str, Any]:
        return {**data, "base_info": {"channel_version": self.settings.channel_version}}

    async def get(self, endpoint: str, *, timeout_s: float | None = None, auth: bool = False) -> dict[str, Any]:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        log.debug("GET %s", redact(url))
        resp = await self.client.get(url, headers=self._common_headers(auth=auth), timeout=timeout_s)
        text = resp.text
        log.debug("GET status=%s body=%s", resp.status_code, redact(text[:800]))
        resp.raise_for_status()
        return json.loads(text) if text else {}

    async def post(self, endpoint: str, data: dict[str, Any], *, timeout_s: float | None = None) -> dict[str, Any]:
        body = json.dumps(self._with_base_info(data), ensure_ascii=False, separators=(",", ":"))
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        log.debug("POST %s body=%s", redact(url), redact(body[:1200]))
        resp = await self.client.post(url, content=body, headers=self._common_headers(body), timeout=timeout_s)
        text = resp.text
        log.debug("POST status=%s body=%s", resp.status_code, redact(text[:1200]))
        resp.raise_for_status()
        return json.loads(text) if text else {}

    async def fetch_qrcode(self, bot_type: str) -> dict[str, Any]:
        # QR code endpoint is fixed to ilinkai.weixin.qq.com in upstream implementation.
        api = WeixinApi(self.settings, base_url="https://ilinkai.weixin.qq.com")
        try:
            return await api.get(f"ilink/bot/get_bot_qrcode?bot_type={bot_type}", auth=False)
        finally:
            await api.close()

    async def poll_qrcode_status(self, qrcode: str, *, timeout_s: float | None = None) -> dict[str, Any]:
        return await self.get(
            f"ilink/bot/get_qrcode_status?qrcode={httpx.QueryParams({'qrcode': qrcode})['qrcode']}",
            timeout_s=timeout_s or self.settings.long_poll_timeout_s,
            auth=False,
        )

    async def get_updates(self, get_updates_buf: str, *, timeout_s: float | None = None) -> dict[str, Any]:
        return await self.post(
            "ilink/bot/getupdates",
            {"get_updates_buf": get_updates_buf or ""},
            timeout_s=timeout_s or self.settings.long_poll_timeout_s,
        )

    async def send_message(self, msg: dict[str, Any]) -> dict[str, Any]:
        return await self.post("ilink/bot/sendmessage", {"msg": msg})

    async def get_upload_url(self, data: dict[str, Any]) -> dict[str, Any]:
        return await self.post("ilink/bot/getuploadurl", data)

    async def get_config(self, ilink_user_id: str, context_token: str | None = None) -> dict[str, Any]:
        return await self.post(
            "ilink/bot/getconfig",
            {"ilink_user_id": ilink_user_id, "context_token": context_token},
        )

    async def send_typing(self, ilink_user_id: str, typing_ticket: str, status: int = 1) -> dict[str, Any]:
        return await self.post(
            "ilink/bot/sendtyping",
            {"ilink_user_id": ilink_user_id, "typing_ticket": typing_ticket, "status": status},
        )
